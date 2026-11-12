import copy,json
from .storage import ROOT,digest,canonical
from .settings_support import SettingsP2
from .settings_support import initial_settings,validate_settings,VERSION

class Settings:
 def __init__(self,store):self.store=store
 def read_write(self,value=None,revision=None,*,include_legacy_assignments=False):
  defaults=json.loads((ROOT/'config/priorities.p3.json').read_text(encoding='utf8'))
  p2=SettingsP2(self.store).read_write();original=initial_settings(self.store.sources());initial=copy.deepcopy(p2);initial['revision']=0
  notes={}
  for m,g in initial['modules'].items():
   customized=g['sources']!=original['modules'][m]['sources'] or any(s['provenance']=='USER_V5' for s in g['sources'])
   notes[m]='PERSONNALISATION_PRESERVEE_DEFAULTS_DISPONIBLES' if customized else 'PRIORITES_P3_RESTAUREES'
   if not customized:g['sources']=copy.deepcopy(defaults['modules'][m])
  with self.store.tx() as db:
   row=db.execute("SELECT value FROM metadata WHERE key='web_selection_p3'").fetchone()
   if row:
    e=json.loads(row[0]);old=e['payload'];notes=e['initialization']
    if e['sha']!=digest({'payload':old,'initialization':notes}):raise ValueError('P3_SETTINGS_CORRUPT')
   else:old=initial
   # Les liens nouveaux utilisent les identifiants stables du catalogue. La
   # résolution du titre/URL ne réécrit pas la configuration technique ni les
   # références historiques indépendantes.
   library_row=db.execute("SELECT value FROM metadata WHERE key='web_sources_e1bis'").fetchone();library={}
   if library_row:
    lib=json.loads(library_row[0])
    if digest(lib['payload'])!=lib['sha']:raise ValueError('WEB_CATALOG_CORRUPT')
    library={s['id']:s for s in lib['payload']['sources']}
   old=copy.deepcopy(old)
   for group in old['modules'].values():
    for source in group['sources']:
     if source['provenance']=='CATALOG_SOURCE':
      entry=library.get(source['id'].removeprefix('catalog_'))
      if entry is None:raise ValueError('P3_LIBRARY_SOURCE_MISSING')
      source.update(title=entry['title'],url=entry['url'])
   pending=[];marker='OCTIES_ASSIGNMENTS_REVIEWED'
   if include_legacy_assignments:
    for module,group in old['modules'].items():
     legacy=sorted([s for s in library.values() if module in s['modules']],key=lambda s:(s['modules'][module],s['id']))
     if legacy and marker not in notes[module]:
      pending.append(module)
      for entry in legacy:
       if not any(s['id']=='catalog_'+entry['id'] or s.get('url') and s['url']==entry['url'] or not s.get('url') and s['title']==entry['title'] for s in group['sources']):
        group['sources'].append({'id':'catalog_'+entry['id'],'title':entry['title'],'url':entry['url'],'provenance':'CATALOG_SOURCE'})
   validate_settings(old,defaults['modules'])
   if value is None:return {'value':old,'initialization':notes,'conditional_preferences':defaults['conditional_preferences'],'defaults':defaults['modules'],'protocol':'gary_v5_preferences_p3_v1','legacy_assignment_review_required':pending}
   if type(revision)is not int or revision!=old['revision']:raise ValueError('REVISION_CONFLICT')
   validate_settings(value,defaults['modules'])
   known={s['id']:s for g in (defaults['modules'].values()) for s in g}
   known.update({s['id']:s for g in p2['modules'].values() for s in g['sources']})
   for g in value['modules'].values():
    for s in g['sources']:
     if s['provenance']=='CATALOG_SOURCE':
      entry=library.get(s['id'].removeprefix('catalog_'))
      if not entry or s['id']!='catalog_'+entry['id'] or s['title']!=entry['title'] or s['url']!=entry['url']:raise ValueError('P3_LIBRARY_SOURCE_INVALID')
     elif s['provenance']!='USER_V5_P2' and known.get(s['id'])!=s:raise ValueError('P3_PROVENANCE_INVALID')
   value=copy.deepcopy(value);value['revision']=old['revision']+1
   if include_legacy_assignments:
    notes=copy.deepcopy(notes)
    for module in pending:notes[module]=notes[module]+'|'+marker
   e={'payload':value,'initialization':notes};e['sha']=digest(e)
   db.execute("INSERT OR REPLACE INTO metadata VALUES('web_selection_p3',?)",(canonical(e),))
  return self.read_write()
