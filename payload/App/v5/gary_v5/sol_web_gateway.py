"""Parcours Sol multi-actions : préparation réelle, émission fermée par défaut."""
from copy import deepcopy
from pathlib import Path
import hashlib,json,secrets,threading,time
from .storage import digest,canonical,ROOT
from .commercial_supervisor import require
from .generation_gateway import GenerationGateway
from .sol_web_profile import apply,validate,preflight
from .sol_web_profile import validate as validate_any
from .sol_web_response import display
from .web_campaign import WebCampaign
from .live_supervisor import TEST_ROOT
from .generation_metrics import metrics

NETWORK_RELEASE=None
TRUSTED_RELEASES=frozenset()
def dependencies():
 names=('sol_web_profile.py','sol_web_response.py','sol_web_gateway.py','web_campaign.py','generation_contract.py','module_rules.py','documentary_cache.py','request_policy.py','luna_routing.py','semantic_cache.py','semantic_contract.py','live_commissioning.py','responses_stream.py')
 paths=[Path(__file__).with_name(n) for n in names]+list((ROOT/'prompts').glob('*.md'))+list((ROOT/'config').glob('*.json'))
 return digest({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})

class SimulatedWebTransport:
 def __init__(self,response=None,error=None,*,responses=None):self.response=response;self.error=error;self.calls=0;self.responses=responses
 def exchange(self,request,campaign,identity,*,capture=None):
  require(campaign.test,'WEB_SIMULATION_TEST_ONLY');campaign.claim_emission(identity,request);self.calls+=1
  if self.error:raise self.error
  value=self.responses(request,self.calls) if callable(self.responses) else self.responses[self.calls-1] if self.responses is not None else self.response
  if capture is not None:
   import io
   from .responses_stream import simulated_chunks
   raw=b''.join(simulated_chunks(value)) if type(value) is dict else value
   return capture.consume(io.BytesIO(raw) if type(raw) is bytes else raw)
  return value if type(value) is bytes else canonical(value).encode('utf8')
class CampaignResponsesTransport:
 def __init__(self,*,release=None):
  if release is not None:
   from .live_commissioning import OwnerRelease
   require(type(release) is OwnerRelease,'WEB_RELEASE_AUTHORITY')
  self.release=release
 def ready(self):return self.release.ready() if self.release is not None else NETWORK_RELEASE is not None and NETWORK_RELEASE in TRUSTED_RELEASES
 def exchange(self,request,campaign,identity,*,capture=None):
  require(not campaign.test and self.ready(),'WEB_NETWORK_SEALED')
  if self.release is not None:self.release.check(request,campaign,identity)
  campaign.claim_emission(identity,request)
  return exchange_once(ROOT/'data',request,capture=capture)

def exchange_once(directory,request,*,capture=None):
 from .windows_vault import Vault,protect
 from .live_transport import _https_once
 secret=bytearray(protect(Vault(directory/'private').path.read_bytes(),decrypt=True))
 try:
  require(secret.startswith(b'sk-') and not any(chr(c).isspace() for c in secret),'CREDENTIAL_INVALID')
  return _https_once(request,secret,capture=capture) if capture is not None else _https_once(request,secret)
 finally:secret[:]=b'\0'*len(secret)

class DirectResponsesTransport:
 def __init__(self,store):
  self.store=store
  self.emission=threading.Lock()
  self.admission=threading.Lock()
 def enabled(self):
  with self.store.tx() as db:
   row=db.execute("SELECT value FROM metadata WHERE key='openai_api_enabled_v1'").fetchone()
  return row is not None and row[0]=='true'
 def set_enabled(self,value):
  require(type(value) is bool,'API_SWITCH_INVALID')
  with self.admission,self.store.tx() as db:
   db.execute("INSERT OR REPLACE INTO metadata VALUES('openai_api_enabled_v1',?)",(canonical(value),))
  return {'enabled':value}
 def ready(self):
  from .windows_vault import Vault
  return self.enabled() and Vault(self.store.root/'private').status()['configured']
 def exchange(self,request,campaign=None,identity=None,*,capture=None):
  from .semantic_contract import validate_request
  require(validate(request) or validate_request(request),'API_REQUEST_INVALID')
  require(self.emission.acquire(blocking=False),'API_OPERATION_IN_PROGRESS')
  try:
   with self.admission:require(self.ready(),'API_DISABLED_OR_KEY_ABSENT')
   return exchange_once(self.store.root,request,capture=capture)
  finally:self.emission.release()

class SolWebGateway:
 """Injectable dans le serveur normal ; aucun paramètre fournisseur navigateur."""
 def __init__(self,runtime,*,campaign=None,allocation=None,expected=None,prudent=None,transport=None,luna_routing=None,direct=False):
  self.base=GenerationGateway(runtime);self.runtime=runtime;self.campaign=campaign;self.allocation=allocation;self.expected=expected;self.prudent=prudent;self.transport=transport or (DirectResponsesTransport(runtime.store) if direct else CampaignResponsesTransport());self.entries={};self.lock=threading.Lock()
  require(campaign is None or type(campaign) is WebCampaign,'WEB_CAMPAIGN_REQUIRED')
  self.direct=type(self.transport) is DirectResponsesTransport
  if self.direct:require(direct and campaign is None and self.transport.store is runtime.store,'API_DIRECT_CONFIGURATION')
  elif type(self.transport) is SimulatedWebTransport:require(campaign is not None and campaign.test and runtime.store.root.is_relative_to(TEST_ROOT.resolve()),'WEB_SIMULATION_TEST_ONLY')
  else:require(type(self.transport) is CampaignResponsesTransport and (campaign is None or not campaign.test),'WEB_TRANSPORT_REFUSED')
  from .luna_routing import LunaRouting
  require(luna_routing is None or type(luna_routing) is LunaRouting and luna_routing.store.root==runtime.store.root and runtime.store.root.is_relative_to(TEST_ROOT.resolve()),'WEB_LUNA_INJECTION_TEST_ONLY')
  self.luna=luna_routing or LunaRouting(runtime.store)
  if self.direct:self.luna.direct=self.transport
 def prepared_request(self,data,*,allow_luna=False):
  from .routing import command_parts
  forced,_=command_parts(data.get('query'),data.get('module','AUTO'))
  if forced is not None and not self.luna.semantic.qualification:
   prepared,request=self.base.prepare_request(data);return prepared,request,None
  require(not data.get('rewrite'),'WEB_PRIVATE_REWRITE_REQUIRES_EXPLICIT_FICH')
  route=self.luna.generation_route(data,allow_emit=allow_luna)
  if route is None and forced is not None:
   values=deepcopy(data)
   if self.luna.semantic.qualification:values.update(module=forced,query=command_parts(data.get('query'),data.get('module','AUTO'))[1])
   prepared,request=self.base.prepare_request(values);return prepared,request,None
  if not route or route.get('status')!='routed':return route,None,None
  if route.get('cache_plan',{}).get('state')=='TEST_SEMANTIC_CR_HIT':
   return self.semantic_result(route,data),None,None
  values=deepcopy(data);body=json.loads(route['prepared_request']['input']);values.update(module=route['module'],query=body['question'],profile=body.get('profile',{}))
  prepared,request=self.base.prepare_request(values)
  anchor={'routing_id':route['routing_id'],'request_sha256':route['request_sha256'],'decision_sha256':route.get('decision_sha256')}
  return prepared,request,anchor
 def semantic_result(self,route,data):
  """Consomme uniquement une décision A2 reconnue, jamais un champ navigateur."""
  require(self.base.cache.test and self.luna.semantic.qualification,'A2_SEMANTIC_PRODUCTION_DISABLED')
  plan=route['cache_plan'];identity=plan['source_entry_id']
  with self.runtime.store.tx() as db:cached,_,_=self.base.cache._row(db,identity,'CR')
  self.base.cache._proof(cached['proof'])
  original=self.luna.semantic.local.rebuild(cached['context']);provider=json.loads((Path(cached['proof']['directory'])/'reponse_fournisseur.json').read_text('utf8'))
  result=display(original,provider,test=True);result['question']=plan['new_question']
  from .documentary_cache import iso
  result['cache']={'kind':'CR','match':'SEMANTIC','entry_id':identity,'generated_at':cached['generated_at'],'read_at':iso(time.time()),
   'original_question':plan['original_question'],'semantic_decision_id':plan['semantic_decision_id'],'clinical_validation':False}
  return self.base.local_result(route['prepared_request'],result,'CACHE_REUSED',data,test=True,evidence=cached['proof']['directory'],origin={'cache_entry':identity,'semantic_decision':plan['semantic_decision_id']})
 def profiled(self,legacy):
  return apply(legacy)
 def current(self,request,refresh=False):
  # Réutilise les contrôles de dépendances et préférences CD/CR existants.
  return self.base.cache_plan(request,allow_cr=not refresh)
 def prepare(self,data):
  allowed={'query','module','profile','privacy_confirmed','depth','context_policy','history_id','rewrite','include_personal_suivi','renal_context','record_history','model','luna_retry'}
  require(type(data) is dict and not set(data)-allowed,'WEB_PREPARATION_FIELDS')
  require('model' not in data or data['model']=='auto-luna-sol','WEB_MODEL_SELECTION_REFUSED')
  if 'luna_retry' in data:
   from .routing import command_parts
   require(self.direct and type(data['luna_retry']) is str and command_parts(data.get('query'),data.get('module','AUTO'))[0] is None,'LUNA_RETRY_INVALID')
  prepared,legacy,route_anchor=self.prepared_request(data,allow_luna=True)
  data={k:v for k,v in data.items() if k!='luna_retry'}
  if legacy is None:return prepared
  request=self.profiled(legacy);request,plan=self.current(request,bool(data.get('history_id')))
  require(validate_any(request),'WEB_PREPARED_INVALID')
  if plan and plan['CR']['decision']=='HIT':
   result=deepcopy(plan['display'])
   if plan['CR'].get('entry_id'):
    with self.runtime.store.tx() as db:cached,_,_=self.base.cache._row(db,plan['CR']['entry_id'],'CR')
    self.base.cache._proof(cached['proof'])
    provider=json.loads((Path(cached['proof']['directory'])/'reponse_fournisseur.json').read_text('utf8'))
    result=display(request,provider,test=self.base.cache.test)
   result['cache']={'kind':'CR',**plan['CR'],'clinical_validation':False}
   return self.base.local_result(request,result,'CACHE_REUSED',data,test=result.get('test',False),evidence=plan.get('evidence_directory'),origin={'cache_entry':plan['CR'].get('entry_id')})
  identity=secrets.token_hex(16);challenge=secrets.token_urlsafe(32)
  ready=self.transport.ready() if self.direct else self.campaign is not None and (self.campaign.test or self.transport.ready())
  if ready and type(self.transport) is CampaignResponsesTransport and self.transport.release is not None:
   try:self.transport.release.check(request,self.campaign)
   except (ValueError,KeyError,TypeError,OSError):ready=False
  test=self.base.cache.test if self.direct else bool(self.campaign and self.campaign.test)
  e={'id':identity,'challenge':challenge,'request':deepcopy(request),'data':deepcopy(data),'sha':digest(request),'created':time.monotonic(),'dependencies':dependencies(),'route_anchor':route_anchor,'used':False,'state':'PREPARED','test':test,'metrics':metrics(test=test)}
  with self.lock:
   self.entries={k:v for k,v in self.entries.items() if v['state'] in ('RESERVED','ENGAGED','EMITTING') or time.monotonic()-v['created']<300}
   require(len(self.entries)<64,'WEB_PREPARATION_CAPACITY');self.entries[identity]=e
  return {**prepared,'request_sha256':e['sha'],'web_preflight':preflight(request),'cache_decisions':{k:plan[k] for k in ('CR','CD')} if plan else None,
   'generation':{'direct':self.direct,'id':identity,'challenge':challenge,'ready':ready,'confirmation':'Confirmer cette génération Sol','test':e['test'],'blockers':[] if ready else (['API désactivée ou clé absente.'] if self.direct else ['Nouvelle autorisation de campagne et ouverture réseau serveur nécessaires.']),'max_builtin_actions':12,'guaranteed_maximum_eur':None,'profile':json.loads(request['input'])['documentary_web_profile'],'metrics':e['metrics']}}
 def status(self,identity):
  with self.lock:
   e=self.entries[identity];return {'stream':deepcopy(e.get('stream',{})),'id':identity,'state':e['state'],'test':e['test'],'retry_allowed':False,'evidence_available':False,'provider_evidence_preserved':'evidence' in e,'metrics':deepcopy(e['metrics']),'phases':[e['state']],'blockers':[]}
 def confirm(self,data):
  require(type(data) is dict and set(data)=={'id','challenge','confirmation'},'WEB_CONFIRM_FIELDS')
  with self.lock:
   e=self.entries.get(data['id']);require(e is not None and secrets.compare_digest(str(data['challenge']),e['challenge']) and data['confirmation']=='Confirmer cette génération Sol','WEB_CONFIRM_REFUSED')
   require(not e['used'],'WEB_SECOND_EMISSION_REFUSED')
   if self.direct:
    require(not any(other.get('claimed_at',0)>=e['created'] and other['sha']==e['sha'] for other in self.entries.values()),'WEB_SECOND_EMISSION_REFUSED')
   require(self.transport.ready() if self.direct else self.campaign is not None and (self.campaign.test or self.transport.ready()),'WEB_NETWORK_SEALED')
   require(time.monotonic()-e['created']<300 and dependencies()==e['dependencies'] and digest(e['request'])==e['sha'],'WEB_PREPARATION_CHANGED')
   _,legacy,anchor=self.prepared_request(e['data']);require(legacy is not None and anchor==e['route_anchor'],'WEB_LUNA_DECISION_CHANGED')
   original=self.profiled(legacy);fresh,plan=self.current(original,bool(e['data'].get('history_id')))
   require(not plan or plan['CR']['decision']!='HIT','WEB_CACHE_CHANGED_REPREPARE')
   require(digest(fresh)==e['sha'],'WEB_DEPENDENCIES_CHANGED')
   if type(self.transport) is CampaignResponsesTransport and self.transport.release is not None:
    self.transport.release.check(fresh,self.campaign)
   if not self.direct:self.campaign.reserve(e['id'],fresh,allocation=self.allocation,expected=self.expected,prudent=self.prudent,dependencies=e['dependencies'])
   e['used']=True;e['claimed_at']=time.monotonic();e['state']='RESERVED'
  if not self.direct:self.campaign.engage(e['id'],fresh,e['dependencies'])
  e['state']='ENGAGED';start=time.perf_counter()
  try:
   from .responses_stream import StreamCapture,StreamFailure
   def progress(capture):
    preview=capture.preview()
    with self.lock:
     e['stream']={'sequence':capture.events,'timings_ms':capture.telemetry(),'preview':None}
     if preview:
      body=json.loads(fresh['input']);e['stream']['preview']={'schema':'gary_sol_web_result_v1','module':body['module'],'question':body['question'],'clinical_validation':False,'test':e['test'],'status':'partial','provider_status':'in_progress','provisional':True,'text':preview,'fragments':[{'text':preview,'annotations':[]}],'references':[],'warnings':['Réponse en cours — provisoire, références non finalisées.'],'web_state':'in_progress'}
   capture=StreamCapture(fresh['model'],progress) if fresh.get('stream') is True else None
   interrupted=False
   try:raw=self.transport.exchange(fresh,self.campaign,e['id'],capture=capture) if capture is not None else self.transport.exchange(fresh,self.campaign,e['id'])
   except StreamFailure:
    if capture is None or capture.partial() is None:raise
    raw=canonical(capture.partial()).encode('utf8');interrupted=True
   exchange_ms=(time.perf_counter()-start)*1000;require(type(raw) is bytes and len(raw)<=8_388_608,'WEB_RESPONSE_SIZE')
   from .live_transport import strict_json
   from .functional_store import privacy_check
   try:provider=strict_json(raw)
   except (ValueError,TypeError):provider=None
   # Comme pour les preuves historiques, aucun secret/identifiant détecté
   # ne doit être écrit en clair, même dans une réponse fournisseur invalide.
   privacy_check(provider if provider is not None else raw.decode('utf8',errors='replace'))
   # Conserver la réponse avant toute adaptation, dans un espace de preuve neuf.
   folder=self.runtime.store.root/'web_response_evidence'/e['id'];folder.mkdir(parents=True,exist_ok=False)
   (folder/'provider_original.json').write_bytes(raw);h=hashlib.sha256(raw).hexdigest()
   if capture is not None:
    privacy_check(bytes(capture.raw).decode('utf8',errors='replace'));(folder/'provider_wire.sse').write_bytes(bytes(capture.raw));e['stream_telemetry']=capture.telemetry()
   (folder/'manifest.json').write_text(canonical({'schema':'gary_web_response_evidence_v1','test':e['test'],'request_sha256':e['sha'],'response_sha256':h,'complete':False}),encoding='utf8')
   e['evidence']=folder
   if not self.direct:
    self.campaign.finish(e['id'],received=not interrupted,response_sha=h)
    if not interrupted and provider is not None:self.campaign.record_usage(e['id'],provider.get('usage'))
   e['state']='UNCERTAIN' if interrupted else 'RECEIVED'
   result=display(fresh,provider,test=e['test'])
   (folder/'generated_text.txt').write_bytes(result['text'].encode('utf8'))
   (folder/'manifest.json').write_text(canonical({'schema':'gary_web_response_evidence_v1','test':e['test'],'request_sha256':e['sha'],'response_sha256':h,'text_sha256':hashlib.sha256(result['text'].encode('utf8')).hexdigest(),'complete':result['status']=='complete','wire_format':'SSE' if capture is not None else 'JSON','provider_json_origin':'RECONSTRUCTED_FROM_SSE' if capture is not None else 'WIRE_ORIGINAL','wire_sha256':hashlib.sha256(bytes(capture.raw)).hexdigest() if capture is not None else None,'terminal_received':capture.terminal if capture is not None else True}),encoding='utf8')
   e['state']='DISPLAYED' if result['status']=='complete' else 'INCOMPLETE'
   if interrupted:
    result['provider_status']='unknown';result['warnings'].append('Flux interrompu sans état terminal fournisseur. Coût incertain ; aucune relance.');e['state']='UNCERTAIN'
   e['metrics']=metrics(provider,{'transport_exchange_ms':exchange_ms},test=e['test'])
   if capture is not None:
    e['metrics'].update(capture.telemetry());e['stream']['preview']=None
   policy=self.runtime.store.preferences()['modules'][result['module']]
   if result['status']=='complete' and (policy['CD']['enabled'] or policy['CR']['enabled']):
    try:
     # Adaptation explicite au contrat de preuve du cache existant. Les
     # originaux natifs et leurs fragments restent conservés séparément.
     from .live_evidence import save_response,manifest_write
     from .generation_contract import display_result
     cache_folder=(self.runtime.store.root/'web_cache_proofs'/e['id']) if e['test'] else self.runtime.store.root/'live_3d/evidence/web_campaigns'/e['id']
     state={'state':'ENGAGED','emissions':1,'test':e['test'],'campaign':(e['id'] if self.direct else self.campaign.snapshot()['authorization']['campaign_id']),'request_sha256':e['sha'],'dependencies':{'native_web':e['dependencies']}}
     save_response(cache_folder,raw,provider,state)
     manifest=json.loads((cache_folder/'manifest.json').read_text('utf8'));manifest.update(gary_version='V5-E1-SEPTIES',producer_profile=json.loads(fresh['input'])['documentary_web_profile'],financial_registry_schema=None if self.direct else 'gary_sol_web_campaign_v1');manifest_write(cache_folder,manifest)
     legacy={**display_result(fresh,provider),'test':e['test']};cached=self.base.cache.capture(fresh,legacy,cache_folder)
     if cached.get('entry_id'):result['cache_entry_id']=cached['entry_id']
    except Exception:result['cache_warning']='Réponse conservée ; alimentation du cache refusée ou indisponible. Aucun nouvel appel.'
   result=self.base.local_result(fresh,result,e['state'],e['data'],test=e['test'],origin={('api_operation' if self.direct else 'web_campaign_operation'):e['id']})
   # La télémétrie technique est ajoutée après le contrôle/enregistrement
   # documentaire : une fraction décimale peut ressembler à un téléphone.
   # Le contenu fournisseur reste intégralement contrôlé avant toute écriture.
   e['metrics']['timings_ms']['local_postprocess_ms']=max(0,(time.perf_counter()-start)*1000-exchange_ms)
   from .windows_vault import atomic_bytes
   atomic_bytes(folder/'performance.json',canonical(e['metrics']).encode('utf8'))
   result['transport_exchange_ms']=exchange_ms
   result['performance']={'timings_ms':e['metrics']['timings_ms'],**e.get('stream_telemetry',{})}
   # Pas d'ingestion automatique de pages ou faux extraits natifs dans CD.
   return {**self.status(e['id']),'display':result,'cost_state':'UNKNOWN','retry_allowed':False}
  except BaseException as exc:
   if not self.direct and self.campaign.snapshot()['operations'][e['id']]['state'] in ('ENGAGED','EMITTING'):self.campaign.finish(e['id'])
   e['state']='UNCERTAIN'
   if isinstance(exc,(KeyboardInterrupt,SystemExit)):raise
   raise RuntimeError('WEB_OPERATION_STOPPED_NO_RETRY') from None
 def client_metrics(self,data):
  import math
  allowed={'confirmation_ms','click_to_receipt_ms','click_to_display_ms','client_render_ms','click_to_first_event_observed_ms','click_to_first_text_ms','first_block_render_ms','click_to_complete_ms','click_to_partial_final_ms'}
  require(type(data) is dict and set(data)=={'id','challenge','metrics'} and type(data['metrics']) is dict and not set(data['metrics'])-allowed,'WEB_METRICS_FIELDS')
  require(all(type(v) in (int,float) and math.isfinite(v) and 0<=v<=86_400_000 for v in data['metrics'].values()),'WEB_METRICS_VALUES')
  with self.lock:
   e=self.entries.get(data['id']);require(e is not None and secrets.compare_digest(str(data['challenge']),e['challenge']) and 'evidence' in e and e['state'] in ('DISPLAYED','INCOMPLETE','UNCERTAIN'),'WEB_METRICS_SCOPE')
   e['metrics']['client_timings_ms']=deepcopy(data['metrics'])
   from .windows_vault import atomic_bytes
   atomic_bytes(e['evidence']/'performance.json',canonical(e['metrics']).encode('utf8'))
  return {'saved':True,'emission':False}
 def capture(self,data):raise ValueError('WEB_VISUAL_EXPORT_NOT_QUALIFIED')
 def artifact(self,identity,name):
  require(name in ('provider_original.json','provider_wire.sse','generated_text.txt','manifest.json','performance.json'),'WEB_ARTIFACT_REFUSED')
  e=self.entries.get(identity);require(e and 'evidence' in e,'WEB_ARTIFACT_ABSENT')
  p=e['evidence']/name;require(p.is_file() and not p.is_symlink() and not p.is_junction(),'WEB_ARTIFACT_REFUSED');return p.read_bytes()
