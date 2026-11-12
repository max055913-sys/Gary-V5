"""Connecteurs techniques E1 quater. Aucune décision de pertinence médicale."""
from copy import deepcopy
import json,time
from .storage import canonical,digest
from .commercial_supervisor import require
from .source_catalog import SourceCatalog,source_policy,professional

from .live_supervisor import TEST_ROOT

def scope(source):
 return digest({key: source[key] for key in ('id', 'url', 'domain', 'access_kind')})

VERSION='gary_source_connector_v1'
OPERATIONS={'search':'search','open_page':'html','retrieve_document':'download','read_pdf':'pdf','inject_sol':'html','store_cd':'html'}
ACCESS=('PUBLIC','PROFESSIONAL','OFFICIAL_API','OTHER')
RIGHTS=('consult','store_cd','inject_sol')
CAPABILITIES=('search','html','pdf','download')

class SourceConnectors:
 def __init__(self,store,*,qualifications=None):
  self.store=store;self.catalog=SourceCatalog(store)
  # Aucun grant juridique distribué par défaut. Injection de preuves uniquement
  # dans des tests explicitement isolés ; jamais par une route navigateur.
  require(qualifications is None or store.root.is_relative_to(TEST_ROOT.resolve()),'CONNECTOR_TEST_ONLY')
  self.qualifications=deepcopy(qualifications or {})
 def key(self,identity):return 'source_connector_v1_'+identity
 def default(self,s):
  access={'PUBLIC':'PUBLIC','API':'OFFICIAL_API','OTHER':'OTHER'}.get(s['access_kind'],'PROFESSIONAL' if s['access_kind'] in ('AUTHENTICATED','SUBSCRIPTION','RESTRICTED') else 'PUBLIC')
  return {'schema':VERSION,'source_id':s['id'],'revision':0,'source_scope_sha256':scope(s),'enabled':s['enabled'],'access_type':access,
    'declared_capabilities':{'search':False,'html':True,'pdf':False,'download':False},
    'declared_rights':{'consult':s['automation_allowed'],'store_cd':s['local_reuse_allowed'],'inject_sol':s['external_ai_allowed']},
    'rights_reference':s['rights_evidence']}
 def _read(self,db,s):
  row=db.execute('SELECT value FROM metadata WHERE key=?',(self.key(s['id']),)).fetchone()
  if not row:return self.default(s)
  envelope=json.loads(row[0]);require(set(envelope)=={'payload','sha'} and digest(envelope['payload'])==envelope['sha'],'CONNECTOR_CORRUPT')
  self.validate(envelope['payload'],s,reading=True);return envelope['payload']
 def validate(self,v,s,reading=False):
  require(type(v) is dict and set(v)==set(self.default(s)) and v['schema']==VERSION and v['source_id']==s['id'],'CONNECTOR_SCHEMA')
  require(type(v['revision']) is int and 0<=v['revision']<9007199254740991 and type(v['enabled']) is bool and v['access_type'] in ACCESS,'CONNECTOR_SCHEMA')
  require(type(v['source_scope_sha256']) is str and len(v['source_scope_sha256'])==64,'CONNECTOR_SCHEMA')
  for name,keys in (('declared_capabilities',CAPABILITIES),('declared_rights',RIGHTS)):
   require(type(v[name]) is dict and set(v[name])==set(keys) and all(type(x) is bool for x in v[name].values()),'CONNECTOR_SCHEMA')
  from .functional_store import privacy_check
  import re
  require(type(v['rights_reference']) is str and len(v['rights_reference'])<=1000,'CONNECTOR_SCHEMA')
  require(not re.search(r'(?:password|mot de passe|cookie|authorization|bearer|token|jeton)\s*[:=]',v['rights_reference'],re.I),'CONNECTOR_SECRET_REFUSED');privacy_check(v['rights_reference'])
 def read(self,identity):
  s=self.catalog.source(identity)
  with self.store.tx() as db:v=self._read(db,s)
  return self.present(s,v)
 def present(self,s,v):
  current=v['source_scope_sha256']==scope(s)
  public=current and v['access_type']=='PUBLIC' and s['access_kind']=='PUBLIC' and not professional(s['domain'])
  # Le transport HTML est celui d'E1 bis ; aucun moteur de recherche, PDF,
  # téléchargement ou authentification n'est qualifié par cette préférence.
  caps={k:('AVAILABLE' if k=='html' and public else 'PREPARED_NOT_QUALIFIED' if k in ('html','pdf','download') else 'UNAVAILABLE') for k in CAPABILITIES}
  grant=self.qualifications.get(s['id'],{})
  valid=grant.get('source_scope_sha256')==scope(s) and grant.get('source_policy_sha256')==source_policy(s) and grant.get('configuration_sha256')==digest(v) and bool(grant.get('provenance')) and grant.get('expires_at',0)>time.time()
  established={k:bool(valid and grant.get('rights',{}).get(k) is True) for k in RIGHTS}
  enabled=s['access_kind']=='PUBLIC' and s['enabled'] and v['enabled']
  operational=enabled and current and caps['html']=='AVAILABLE' and v['declared_capabilities']['html'] and v['declared_rights']['consult'] and established['consult']
  return {'value':deepcopy(v),'configuration_sha256':digest(v),'source_policy_sha256':source_policy(s),'scope_current':current,
   'effective_enabled':enabled,'capabilities':caps,'rights_established':established,'qualification_provenance':grant.get('provenance') if valid else None,
   'account_reference':{'source_id':s['id'],'scope_sha256':scope(s)},'state':'DISABLED' if not enabled else 'SOURCE_CHANGED' if not current else 'AVAILABLE' if operational else 'ACCESS_NOT_QUALIFIED' if not public else 'RIGHTS_QUALIFICATION_REQUIRED',
   'capability_provenance':{'adapter':'E1_BIS_NATIVE_HTML','limitations':'NO_JS_CSS_RENDER_NO_COMPLEX_CONTENT','qualification_version':VERSION},
   'automatic_authentication':False,'medical_sufficiency_evaluated':False}
 def save(self,identity,value,revision):
  s=self.catalog.source(identity)
  require(s['access_kind']=='PUBLIC','PROFESSIONAL_ACCESS_ARCHIVED')
  self.validate(value,s)
  require(type(revision) is int and value['revision']==revision and value['source_scope_sha256']==scope(s),'CONNECTOR_REVISION_OR_SCOPE')
  expected={'PUBLIC':'PUBLIC','API':'OFFICIAL_API','OTHER':'OTHER'}.get(s['access_kind'],'PROFESSIONAL' if s['access_kind'] in ('AUTHENTICATED','SUBSCRIPTION','RESTRICTED') else 'PUBLIC')
  require(value['access_type']==expected,'CONNECTOR_ACCESS_MISMATCH')
  with self.store.tx() as db:
   old=self._read(db,s);require(old['revision']==revision,'REVISION_CONFLICT')
   # La source est relue dans la même transaction que la réservation CAS.
   from .source_catalog import KEY
   row=db.execute('SELECT value FROM metadata WHERE key=?',(KEY,)).fetchone()
   require(row is not None,'CONNECTOR_CATALOG_SAVE_REQUIRED');catalog=json.loads(row[0]);require(digest(catalog['payload'])==catalog['sha'],'CONNECTOR_CORRUPT')
   require(any(x==s for x in catalog['payload']['sources']),'CONNECTOR_SOURCE_CHANGED')
   # Une seule édition des déclarations : synchronisation atomique avec les
   # champs techniques historiques consommés par E1 bis. Aucune preuve n'est
   # créée et aucune priorité médicale n'est modifiée.
   declarations={'automation_allowed':value['declared_rights']['consult'],'local_reuse_allowed':value['declared_rights']['store_cd'],'external_ai_allowed':value['declared_rights']['inject_sol'],'rights_evidence':value['rights_reference']}
   if any(s[k]!=v for k,v in declarations.items()):
    updated=deepcopy(catalog['payload']);updated['revision']+=1
    next(x for x in updated['sources'] if x['id']==identity).update(declarations)
    db.execute('UPDATE metadata SET value=? WHERE key=?',(canonical({'payload':updated,'sha':digest(updated)}),KEY))
   self._write(db,s,old,value)
  result=self.read(identity);catalog=self.catalog.read()['value'];result['catalog_revision']=catalog['revision'];result['catalog_source']=next(s for s in catalog['sources'] if s['id']==identity)
  return result
 def _write(self,db,source,old,value):
  identity=source['id'];revision=old['revision']
  history={'source':source,'configuration':old,'recorded_at':time.time()}
  db.execute('INSERT INTO metadata VALUES(?,?)',('source_connector_history_v1_'+identity+'_'+str(revision),canonical({'payload':history,'sha':digest(history)})))
  saved={**deepcopy(value),'revision':revision+1}
  db.execute('INSERT OR REPLACE INTO metadata VALUES(?,?)',(self.key(identity),canonical({'payload':saved,'sha':digest(saved)})))
  db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('CONNECTOR_SAVED',canonical({'source_id':identity,'before':digest(old),'after':digest(saved)}),time.time()))

 def save_public(self,data):
  """Commit a public catalogue entry and its connector with both draft revisions."""
  import re
  require(set(data)=={'source','connector','catalog_revision','preferences_sha256','operation_id'},'WEB_SOURCE_SAVE_FIELDS')
  operation=data['operation_id']
  require(type(operation) is str and re.fullmatch('[a-f0-9-]{36}',operation),'WEB_SOURCE_SAVE_OPERATION')
  fingerprint=digest(data);key='web_source_save_v1_'+operation

  def receipt(db):
   row=db.execute('SELECT value FROM metadata WHERE key=?',(key,)).fetchone()
   if row is None:return None
   saved=json.loads(row[0])
   require(saved['sha']==digest(saved['payload']),'WEB_SOURCE_SAVE_CORRUPT')
   require(saved['payload']['request_sha256']==fingerprint,'WEB_SOURCE_SAVE_OPERATION_REUSED')
   return {**saved['payload'],'replayed':True}

  with self.store.tx() as db:
   replay=receipt(db)
  if replay is not None:return replay
  source=deepcopy(data['source']);connector=deepcopy(data['connector'])
  require(type(source) is dict and source.get('access_kind')=='PUBLIC','WEB_PUBLIC_SOURCE_REQUIRED')
  require(type(connector) is dict,'CONNECTOR_SCHEMA')
  self.validate(connector,source)
  require(connector['access_type']=='PUBLIC','WEB_PUBLIC_SOURCE_REQUIRED')
  identity=source['id']
  source.update(enabled=connector['enabled'],
                automation_allowed=connector['declared_rights']['consult'],
                local_reuse_allowed=connector['declared_rights']['store_cd'],
                external_ai_allowed=connector['declared_rights']['inject_sol'],
                rights_evidence=connector['rights_reference'])
  value=self.catalog.read()['value']
  previous=next((entry for entry in value['sources'] if entry['id']==identity),None)
  require(previous is None or previous['access_kind']=='PUBLIC','WEB_HISTORICAL_SOURCE_READ_ONLY')
  require(source['modules']==(previous['modules'] if previous else {}),'WEB_SOURCE_ASSIGNMENTS_CHANGED')
  value['preferences_sha256']=data['preferences_sha256']
  value['sources']=[source if entry['id']==identity else entry for entry in value['sources']]
  if previous is None:value['sources'].append(source)

  def commit_connector(db,current,saved):
   require(receipt(db) is None,'REVISION_CONFLICT')
   old_source=next((entry for entry in current['sources'] if entry['id']==identity),None)
   old=self._read(db,old_source or source)
   require(old['revision']==connector['revision'],'REVISION_CONFLICT')
   require(connector['source_scope_sha256']==(old['source_scope_sha256'] if old_source else '0'*64),'REVISION_CONFLICT')
   updated={**connector,'source_scope_sha256':scope(source)}
   self._write(db,old_source or source,old,updated)
   result={'saved':True,'source_id':identity,'catalog_revision':saved['revision'],
           'connector_revision':old['revision']+1,'request_sha256':fingerprint}
   db.execute('INSERT INTO metadata VALUES(?,?)',(key,canonical({'payload':result,'sha':digest(result)})))
   return result

  try:
   return self.catalog.save(value,data['catalog_revision'],after_write=commit_connector)
  except ValueError as error:
   if str(error) not in ('REVISION_CONFLICT','WEB_PREFERENCES_CHANGED'):raise
   with self.store.tx() as db:
    replay=receipt(db)
   if replay is not None:return replay
   raise
 def authorize(self,identity,operation,expected_sha=None):
  require(operation in OPERATIONS,'CONNECTOR_OPERATION_UNKNOWN');env=self.read(identity);v=env['value']
  require(expected_sha is None or env['configuration_sha256']==expected_sha,'CONNECTOR_CONFIGURATION_CHANGED')
  require(env['effective_enabled'],'CONNECTOR_DISABLED');require(env['scope_current'],'CONNECTOR_SOURCE_CHANGED')
  cap=OPERATIONS[operation];require(v['declared_capabilities'][cap] and env['capabilities'][cap]=='AVAILABLE','CONNECTOR_CAPABILITY_NOT_QUALIFIED')
  rights=['consult']+([operation] if operation in ('inject_sol','store_cd') else [])
  require(all(v['declared_rights'][k] and env['rights_established'][k] for k in rights),'CONNECTOR_RIGHTS_NOT_ESTABLISHED')
  return env
 def plan(self,module):
  return [self.read(s['id']) for s in self.catalog.plan(module,strict_legacy=False) if self.read(s['id'])['effective_enabled']]

class DocumentaryTools:
 """Interface serveur future pour Sol. Aucun transport IA ni accès libre."""
 def __init__(self,service,connectors):self.service=service;self.connectors=connectors
 def execute(self,command):
  require(type(command) is dict and set(command)=={'schema','source_id','operation','configuration_sha256','nonce'} and command['schema']=='gary_documentary_tool_v1','CONNECTOR_TOOL_SCHEMA')
  identity=command['source_id'];operation=command['operation'];env=self.connectors.authorize(identity,operation,command['configuration_sha256'])
  require(operation=='open_page','CONNECTOR_TOOL_NOT_OPERATIONAL')
  source=self.service.catalog.source(identity)
  if source['local_reuse_allowed']:self.connectors.authorize(identity,'store_cd',env['configuration_sha256'])
  if source['external_ai_allowed']:self.connectors.authorize(identity,'inject_sol',env['configuration_sha256'])
  # URL provenant du catalogue, jamais du modèle. E1 bis contrôle DNS,
  # redirections, robots, TLS, taille, types et structures complexes.
  result=self.service.probe(identity,command['nonce'])
  self.connectors.authorize(identity,operation,env['configuration_sha256'])
  return {'schema':'gary_documentary_tool_result_v1','configuration_sha256':env['configuration_sha256'],'result':result,'content_is_instruction':False,'medical_sufficiency':'SOL_ONLY'}
 def prepare_context(self,request,acquisitions):
  checked=[]
  for identity in acquisitions:
   with self.service.store.tx() as db:job,_,_=self.service.cache._row(db,identity,'WEB_CHECK_V1')
   require(job.get('origin')=='CONFIGURED','CONNECTOR_COMPLEMENTARY_RIGHTS_REQUIRE_QUALIFICATION')
   sid=job['source']['id'];env=self.connectors.authorize(sid,'inject_sol');self.connectors.authorize(sid,'store_cd');checked.append((sid,env['configuration_sha256']))
  result=self.service.prepare_context(request,acquisitions)
  for sid,h in checked:self.connectors.authorize(sid,'inject_sol',h)
  return result
