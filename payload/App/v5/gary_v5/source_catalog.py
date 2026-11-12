"""Catalogue d'accès E1 bis, extension locale des préférences conservées."""
from copy import deepcopy
import json,re,time,uuid
from urllib.parse import urlsplit
from .storage import canonical,digest
from .settings import Settings
from .module_rules import RULES
from .commercial_supervisor import require
from .functional_store import privacy_check
from .documentary_cache import DocumentaryCache
from .public_acquisition import public_url

KEY='web_sources_e1bis'
VERSION='gary_web_sources_e1bis_v1'
FIELDS={'id','title','url','domain','modules','enabled','access_kind','automation_allowed','local_reuse_allowed','external_ai_allowed','rights_evidence'}

def source_policy(source):return digest({k:v for k,v in source.items() if k!='modules'})

def url_identity(value):
 if value is None:return None
 try:return public_url(value)
 except ValueError:return value

def url_groups(sources):
 groups={}
 for source in sources:
  key=url_identity(source['url'])
  if key is not None:groups.setdefault(key,set()).add(source['id'])
 return groups

def professional(host):return any(host==h or host.endswith('.'+h) for h in ('vidal.fr','vidalfrance.com','ebmfrance.net'))

class SourceCatalog:
 def __init__(self,store):self.store=store;self.cache=DocumentaryCache(store)
 def read(self):
  preferences=Settings(self.store).read_write()['value'];baseline=digest(preferences)
  with self.store.tx() as db:row=db.execute('SELECT value FROM metadata WHERE key=?',(KEY,)).fetchone()
  if row:
   e=json.loads(row[0]);require(digest(e['payload'])==e['sha'],'WEB_CATALOG_CORRUPT');value=e['payload']
  else:
   # Une référence prioritaire initiale n'est pas un connecteur enregistré.
   # Les anciennes lignes persistées, leurs identifiants et affectations sont
   # conservés ; aucune migration destructive à la lecture.
   value={'schema':VERSION,'revision':0,'preferences_sha256':baseline,'sources':[]}
  return {'value':deepcopy(value),'current_preferences_sha256':baseline,'preferences_diverged':value['preferences_sha256']!=baseline}
 def save(self,value,revision,*,remove_module_references=False,after_write=None):
  require(type(value) is dict and set(value)=={'schema','revision','preferences_sha256','sources'} and value['schema']==VERSION,'WEB_CATALOG_SCHEMA')
  env=self.read();old=env['value'];require(type(revision) is int and revision==old['revision'],'REVISION_CONFLICT')
  require(value['preferences_sha256']==env['current_preferences_sha256'],'WEB_PREFERENCES_CHANGED')
  require(type(value['sources']) is list and len(value['sources'])<=200,'WEB_SOURCE_LIMIT');ids=set()
  for s in value['sources']:
   require(type(s) is dict and set(s)==FIELDS,'WEB_SOURCE_SCHEMA');require(type(s['id']) is str and re.fullmatch(r'[a-zA-Z0-9_-]{1,80}',s['id']) and s['id'] not in ids,'WEB_SOURCE_ID');ids.add(s['id'])
   require(type(s['title']) is str and 0<len(s['title'].strip())<=300,'WEB_SOURCE_TITLE')
   if s['url'] is not None:
    try:url=public_url(s['url'])
    except ValueError:
     previous=next((x for x in old['sources'] if x['id']==s['id']),None)
     require(previous is not None and previous['url']==s['url'] and not any(s[k] for k in ('automation_allowed','local_reuse_allowed','external_ai_allowed')),'WEB_HTTPS_PUBLIC_REQUIRED');url=s['url']
    host=urlsplit(url).hostname
    require(type(s['domain']) is str and (host==s['domain'] or host.endswith('.'+s['domain'])),'WEB_DOMAIN_MISMATCH')
   else:require(s['domain']=='','WEB_DOMAIN_MISMATCH')
   require(type(s['modules']) is dict and not set(s['modules'])-set(RULES),'WEB_MODULES')
   require(all(type(v) is int and 1<=v<=10000 for v in s['modules'].values()),'WEB_PRIORITY')
   require(s['access_kind'] in ('UNKNOWN','PUBLIC','AUTHENTICATED','SUBSCRIPTION','RESTRICTED','API','OTHER'),'WEB_ACCESS_KIND')
   require(all(type(s[k]) is bool for k in ('enabled','automation_allowed','local_reuse_allowed','external_ai_allowed')),'WEB_FLAGS')
   require(type(s['rights_evidence']) is str and len(s['rights_evidence'])<=1000,'WEB_RIGHTS_REFERENCE')
   require(not re.search(r'(?:password|mot de passe|cookie|authorization|bearer|token|jeton)\s*[:=]',canonical(s),re.I),'WEB_SECRET_FIELDS_REFUSED');privacy_check(s)
  old_groups=url_groups(old['sources'])
  for key,identities in url_groups(value['sources']).items():
   require(len(identities)==1 or identities<=old_groups.get(key,set()),'WEB_DUPLICATE_URL')
  saved=deepcopy(value);saved['revision']=revision+1
  with self.store.tx() as db:
   row=db.execute('SELECT value FROM metadata WHERE key=?',(KEY,)).fetchone()
   current=json.loads(row[0])['payload'] if row else old
   require(current['revision']==revision,'REVISION_CONFLICT')
   if row:require(json.loads(row[0])['sha']==digest(current),'WEB_CATALOG_CORRUPT')
   removed={s['id'] for s in current['sources']}-{s['id'] for s in saved['sources']}
   if removed:
    preferences_row=db.execute("SELECT value FROM metadata WHERE key='web_selection_p3'").fetchone()
    if preferences_row:
     preferences=json.loads(preferences_row[0]);require(preferences['sha']==digest({'payload':preferences['payload'],'initialization':preferences['initialization']}),'P3_SETTINGS_CORRUPT')
     linked={'catalog_'+identity for identity in removed}
     used=any(s['provenance']=='CATALOG_SOURCE' and s['id'] in linked for group in preferences['payload']['modules'].values() for s in group['sources'])
     require(not used or remove_module_references,'WEB_SOURCE_IN_USE')
     if used:
      for group in preferences['payload']['modules'].values():group['sources']=[s for s in group['sources'] if not (s['provenance']=='CATALOG_SOURCE' and s['id'] in linked)]
      preferences['payload']['revision']+=1;preferences['sha']=digest({'payload':preferences['payload'],'initialization':preferences['initialization']})
      db.execute("UPDATE metadata SET value=? WHERE key='web_selection_p3'",(canonical(preferences),))
   self.cache._put(db,'WEB_CONFIG_HISTORY',{'created_at':time.time(),'configuration':current},'WEB_CONFIG_'+digest(current))
   db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(KEY,canonical({'payload':saved,'sha':digest(saved)})))
   db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('WEB_SOURCES_SAVED',digest(saved),time.time()))
   if after_write is not None:return after_write(db,current,saved)
  return self.read()
 def source(self,identity):
  env=self.read()
  matches=[s for s in env['value']['sources'] if s['id']==identity];require(len(matches)==1,'WEB_SOURCE_ABSENT');return matches[0]
 def plan(self,module,*,strict_legacy=True):
  require(module in RULES,'WEB_MODULE_INVALID');env=self.read()
  if strict_legacy:require(not env['preferences_diverged'],'WEB_PREFERENCES_CHANGED')
  ranked={};preferences=Settings(self.store).read_write()['value']['modules'][module]['sources']
  for rank,p in enumerate(preferences,1):
   for s in env['value']['sources']:
    if p['id']=='catalog_'+s['id'] or p.get('url') and p['url']==s['url'] or not p.get('url') and p['title']==s['title']:ranked.setdefault(s['id'],rank)
  # Compatibilité des anciennes affectations, conservées et non réécrites.
  reviewed='OCTIES_ASSIGNMENTS_REVIEWED' in Settings(self.store).read_write()['initialization'][module]
  for s in env['value']['sources']:
   if module in s['modules'] and (strict_legacy or not reviewed):ranked.setdefault(s['id'],len(preferences)+s['modules'][module])
  return sorted([s for s in env['value']['sources'] if s['enabled'] and s['id'] in ranked],key=lambda s:(ranked[s['id']],s['id']))
