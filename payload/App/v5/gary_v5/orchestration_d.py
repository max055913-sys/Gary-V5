"""Phase D exclusivement synthétique : budget global, A2/C et Gateway Sol.

Aucune route HTTP ou autorisation réseau. Un Store sous TEST_ROOT est obligatoire.
"""
from copy import deepcopy
import json,time
from .storage import digest,canonical
from .commercial_supervisor import require,OfflineSupervisor
from .documentary_cache import DocumentaryCache,bytes_sha
from pathlib import Path
from .semantic_cache import SemanticCache,SimulatedLunaDecision
from .generation_gateway import GenerationGateway
from .application import Runtime
from .live_supervisor import prepare_live_request

ENABLED=False
GLOBAL_ID='D_GLOBAL_OFFLINE_CAMPAIGN'

class GlobalFixtureBudget:
 def __init__(self,store):
  self.store=store;self.cache=DocumentaryCache(store);require(self.cache.test,'D_OFFLINE_ONLY')
 def _load(self,db):
  v=self.cache._row(db,GLOBAL_ID,'D_GLOBAL_V1')[0];previous='0'*64;last=None
  for (raw,) in db.execute("SELECT reference FROM events WHERE event='D_BUDGET' ORDER BY sequence"):
   event=json.loads(raw);require(event['previous']==previous and event['sha']==digest([event['state_sha'],previous]),'D_AUDIT_CORRUPT');previous=event['sha'];last=event
  require(last is not None and last['state_sha']==digest(v),'D_BUDGET_CORRUPT')
  return v
 def _save(self,db,v):
  row=db.execute("SELECT reference FROM events WHERE event='D_BUDGET' ORDER BY sequence DESC LIMIT 1").fetchone()
  previous=json.loads(row[0])['sha'] if row else '0'*64;state_sha=digest(v)
  self.cache._put(db,'D_GLOBAL_V1',v,GLOBAL_ID)
  db.execute('INSERT INTO events(event,reference,time) VALUES(?,?,?)',('D_BUDGET',canonical({'state_sha':state_sha,'previous':previous,'sha':digest([state_sha,previous])}),time.time()))
 def authorize_fixture(self,ceiling,max_attempts=2):
  require(type(ceiling) is int and ceiling>0 and type(max_attempts) is int and max_attempts>0,'D_BUDGET_INVALID')
  with self.store.tx() as db:
   require(not db.execute('SELECT 1 FROM entries WHERE id=?',(GLOBAL_ID,)).fetchone(),'D_CAMPAIGN_ALREADY_EXISTS')
   require(not db.execute("SELECT 1 FROM events WHERE event='D_BUDGET'").fetchone(),'D_CAMPAIGN_RESET_REFUSED')
   self._save(db,{'schema':'gary_global_fixture_budget_d_v1','test':True,'created_at':time.time(),'expires_at':time.time()+1800,'status':'AUTHORIZED_FIXTURE','ceiling':ceiling,'max_attempts':max_attempts,'operations':{}})
 def snapshot(self):
  with self.store.tx() as db:return self._load(db)
 def claim_qualified_fixture(self,identity,request,**conversion):
  # E1 ne délivre aucune autorisation réelle : conversion explicitement simulée.
  from .qualification_e1 import fixture_eur_bound
  proof=fixture_eur_bound(request,**conversion)
  self.claim(identity,request,proof['max_eur_micros'])
  return proof
 def revoke_fixture(self):
  with self.store.tx() as db:
   v=self._load(db);v['status']='REVOKED';self._save(db,v)
 def reserve_workflow_fixture(self,requests,**conversion):
  from .qualification_e1 import fixture_eur_bound
  require(type(requests) is dict and set(requests)=={'luna','sol'},'E1_WORKFLOW_SCOPE')
  require(requests['luna'].get('model')=='gpt-6-luna' and requests['sol'].get('model')=='gpt-6.1-sol','E1_WORKFLOW_MODEL_ROLES')
  proofs={name:fixture_eur_bound(request,**conversion) for name,request in requests.items()}
  with self.store.tx() as db:
   v=self._load(db)
   require(v['status']=='AUTHORIZED_FIXTURE' and time.time()<v['expires_at'],'D_CAMPAIGN_NOT_AUTHORIZED')
   require(not any(x['state']=='UNKNOWN' for x in v['operations'].values()),'D_UNCERTAIN_COST_BLOCKS')
   ids={name:'E1_'+name+'_'+proof['request_sha256'] for name,proof in proofs.items()}
   require(not any(i in v['operations'] for i in ids.values()),'D_SECOND_ATTEMPT_REFUSED')
   cost=sum(x.get('actual',x['reserved']) for x in v['operations'].values())+sum(p['max_eur_micros'] for p in proofs.values())
   require(cost<=v['ceiling'] and len(v['operations'])+2<=v['max_attempts'],'D_GLOBAL_BUDGET_EXCEEDED')
   for name,proof in proofs.items():v['operations'][ids[name]]={'request_sha256':proof['request_sha256'],'model':proof['model'],'reserved':proof['max_eur_micros'],'state':'COMMITTED'}
   self._save(db,v)
  return {'kind':'E1_OFFLINE_WORKFLOW','proofs':proofs,'live_authorized':False}
 def claim(self,identity,request,amount):
  with self.store.tx() as db:
   v=self._load(db)
   require(v['status']=='AUTHORIZED_FIXTURE' and time.time()<v['expires_at'],'D_CAMPAIGN_NOT_AUTHORIZED')
   require(type(amount) is int and amount>0,'D_BOUND_INVALID')
   require(identity not in v['operations'],'D_SECOND_ATTEMPT_REFUSED')
   require(not any(x['state']=='UNKNOWN' for x in v['operations'].values()),'D_UNCERTAIN_COST_BLOCKS')
   cost=sum(x.get('actual',x['reserved']) for x in v['operations'].values())
   require(len(v['operations'])<v['max_attempts'] and cost+amount<=v['ceiling'],'D_GLOBAL_BUDGET_EXCEEDED')
   v['operations'][identity]={'request_sha256':digest(request),'model':request['model'],'reserved':amount,'state':'COMMITTED'}
   self._save(db,v)
 def finish(self,identity,*,actual=None):
  with self.store.tx() as db:
   v=self._load(db);op=v['operations'][identity]
   if actual is None:op['state']='UNKNOWN'
   else:
    require(type(actual) is int and actual>=0,'D_RECEIPT_INVALID')
    require(op.get('actual',actual)==actual,'D_RECEIPT_CHANGED');op.update(state='RECONCILED',actual=actual)
    if actual>op['reserved']:v['status']='FROZEN'
   self._save(db,v)

class OfflineOrchestrator:
 def __init__(self,store,*,scenario='complete'):
  self.store=store;self.cache=DocumentaryCache(store);require(self.cache.test,'D_OFFLINE_ONLY')
  self.semantic=SemanticCache(store,enabled=True,require_auto_decision=True)
  self.budget=GlobalFixtureBudget(store);self.gateway=GenerationGateway(Runtime(store),test_directory=store.root/'d_runs',scenario=scenario,fixture_model_identity=True)
 def _routing_data(self,data):
  # Les surcharges FICH restent traitées par le vrai préparateur, jamais copiées vers Luna.
  return {k:deepcopy(v) for k,v in data.items() if k not in ('rewrite','record_history','model')}
 def begin(self,data):
  route_data=self._routing_data(data);forced,_=self.semantic._mode(route_data)
  saved=self._saved_route(data)
  if saved is not None:return {'state':'RESOLVED','module':saved['module'],'routing_id':saved['route_id']}
  if data.get('rewrite'):
   require(forced=='FICH','D_PRIVATE_REWRITE_REQUIRES_FICH');return {'state':'DIRECT','module':'FICH'}
  p=self.semantic.prepare(route_data)
  return {'state':'DIRECT','module':forced} if forced and p['state'] in ('EXACT_CR','EXACT_CD','MISS','CLARIFICATION') else p
 def classify_simulated(self,proposal,*,supervisor,bound,transport,receipt=None):
  require(type(supervisor) is OfflineSupervisor and type(transport) is SimulatedLunaDecision,'D_OFFLINE_ONLY')
  identity=proposal['operation_id'];request=proposal['request']
  require(bound.get('kind')=='OFFLINE_FIXTURE' and bound.get('qualified') is True and bound.get('request_sha256')==digest(request) and bound.get('model')==request['model'],'D_BOUND_INVALID')
  self.budget.claim(identity,request,bound['max_eur_micros'])
  try:
   result=self.semantic.compare_simulated(identity,supervisor=supervisor,bound=bound,transport=transport,receipt=receipt)
   op=supervisor.snapshot()['operations'].get(identity,{})
   self.budget.finish(identity,actual=op['actual_eur_micros'] if op.get('state')=='RECONCILED' else None)
   return result
  except BaseException:
   self.budget.finish(identity);raise
 def _request(self,data,module):
  values=deepcopy(data);values['module']=module
  _,query=self.semantic._mode(self._routing_data(data));values['query']=query
  p,r=self.gateway.prepare_request(values);require(r is not None,'D_CONTEXT_CLARIFICATION')
  r['input']=canonical(json.loads(r['input']));return values,p,prepare_live_request(r)
 def prepare(self,data,*,routing_id=None):
  route_data=self._routing_data(data);forced,_=self.semantic._mode(route_data);roots=[];route=None
  if routing_id:
   saved=self._saved_route(data,routing_id)
   route={'state':'RESOLVED_MODULE','module':saved['module'],'documents':[]} if saved is not None else self.semantic.confirm(routing_id,route_data)
   if route['state']=='CLARIFICATION':return {'state':'CLARIFICATION'}
   module=route['module']
   if route['state'] in ('EXACT_CR','TEST_SEMANTIC_CR_HIT'):
    _,_,request=self._request(data,module)
    plan=route.get('plan',{});display=deepcopy(plan.get('display',route.get('display')))
    display['cache']={'kind':'CR','routing_id':routing_id,'original_question':display['question'],'clinical_validation':False}
    display=self.gateway.local_result(request,display,'CACHE_REUSED',data,test=True,evidence=plan.get('evidence_directory'),origin={'semantic_decision':routing_id})
    return {'state':'CACHE_HIT','display':display,'sol_calls':0}
  else:
   require(forced is not None,'D_LUNA_DECISION_REQUIRED');module=forced
   p=self.begin(data);require(p['state']=='DIRECT','D_SEMANTIC_DECISION_REQUIRED')
  values,prepared,target=self._request(data,module)
  if route and route.get('documents'):
   candidates={c['id']:c for c in self.semantic._fresh(self.semantic._operation(routing_id),route_data)['candidates']}
   for d in route.get('documents',[]):
    c=candidates[d['entry_id']]
    # Pas de copie de texte ou remise à zéro du TTL : référence à la même preuve.
    self.cache.select_document(target,c['original_request'],c['id'],c['row_sha256'],routing_id)
    roots.append({'id':c['id'],'sha':c['row_sha256'],'request':c['original_request']})
  result=self.gateway.prepare(values)
  if result.get('cache',{}).get('decision')=='HIT':return {'state':'CACHE_HIT','display':result,'sol_calls':0}
  require('generation' in result,'D_CONTEXT_CLARIFICATION')
  g=result['generation'];entry=self.gateway.entries[g['id']];identity='D_SOL_'+digest([data,entry['sha']])
  v={'created_at':time.time(),'schema':'gary_preparation_d_v1','implementation_sha256':bytes_sha(Path(__file__)),'data':deepcopy(data),'resolved':values,'module':module,'request':entry['request'],'request_sha256':entry['sha'],'confirmation':{k:g[k] for k in ('id','challenge','confirmation')},'state':'PREPARED','route_id':routing_id,'roots':roots,'gateway_entry_id':g['id'],'directory':None}
  if routing_id:
   op=self.semantic._operation(routing_id);v['route_anchor']={'request_sha':digest(op['request']),'decision_sha':op['decision_sha256']}
  with self.store.tx() as db:
   v['configuration_sha256']=self.cache._dependency(db,entry['request'])
   if not db.execute('SELECT 1 FROM entries WHERE id=?',(identity,)).fetchone():self.cache._put(db,'D_PREPARATION_V1',v,identity)
   else:v=self.cache._row(db,identity,'D_PREPARATION_V1')[0]
  return {'state':v['state'],'id':identity,'confirmation':v['confirmation'],'request_sha256':v['request_sha256'],'module':module,'network_enabled':False}
 def _read(self,identity):
  with self.store.tx() as db:return self.cache._row(db,identity,'D_PREPARATION_V1')[0]
 def _saved_route(self,data,routing_id=None):
  # L'ajout de candidats après notre génération n'invalide pas à lui seul
  # une classification. Les nouvelles admissions CR/CD restent contrôlées.
  for row in self.store.rows('D_PREPARATION_V1'):
   v=row['data']
   if not v.get('route_id') or digest(v['data'])!=digest(data) or (routing_id and v['route_id']!=routing_id):continue
   try:
    self._route_binding(v)
    return v
   except (ValueError,KeyError,OSError):continue
  return None
 def _route_binding(self,v):
  require(v['implementation_sha256']==bytes_sha(Path(__file__)),'D_IMPLEMENTATION_CHANGED')
  _,_,request=self._request(v['data'],v['module'])
  old,_=self.cache._base(v['request']);current,_=self.cache._base(request)
  require(digest(old)==digest(current),'D_ROUTE_CONTEXT_CHANGED')
  with self.store.tx() as db:
   require(v['configuration_sha256']==self.cache._dependency(db,current),'D_ROUTE_CONFIGURATION_CHANGED')
  op=self.semantic._operation(v['route_id']);require(op['state']=='DECIDED' and time.time()<op['expires_at'],'D_ROUTE_EXPIRED')
  require(digest(op['data'])==digest(self._routing_data(v['data'])) and digest(op['request'])==v['route_anchor']['request_sha'] and digest(op['decision'])==op['decision_sha256']==v['route_anchor']['decision_sha'],'D_ROUTE_CHANGED')
  finance=OfflineSupervisor(op['supervisor_path']).snapshot();f=finance['operations'][v['route_id']]
  require(finance['campaign']['status']=='AUTHORIZED' and f['state']=='RECONCILED' and f['request_sha256']==digest(op['request']) and f['result_sha256']==op['response_fingerprint'],'D_ROUTE_FINANCE_CHANGED')
  for root in v['roots']:
   plan=self.cache.resolve(root['request'],allow_cr=False)
   require(any(d['id']==root['id'] and d['sha256']==root['sha'] for d in plan['dependencies']),'D_DOCUMENT_DEPENDENCY_CHANGED')
 def _verify(self,v):
  require(v['implementation_sha256']==bytes_sha(Path(__file__)),'D_IMPLEMENTATION_CHANGED')
  require(0<=time.time()-v['created_at']<=30,'D_PREPARATION_EXPIRED')
  _,_,request=self._request(v['data'],v['module'])
  for root in v['roots']:
   plan=self.cache.resolve(root['request'],allow_cr=False)
   require(any(d['id']==root['id'] and d['sha256']==root['sha'] for d in plan['dependencies']),'D_DOCUMENT_DEPENDENCY_CHANGED')
  if v['route_id']:
   self._route_binding(v)
  plan=self.cache.resolve(request,allow_cr=False);request=self.cache.enrich(request,plan)
  require(digest(request)==v['request_sha256'],'D_PREPARED_REQUEST_CHANGED')
 def confirm_sol(self,identity,confirmation):
  v=self._read(identity);require(confirmation==v['confirmation'],'D_CONFIRMATION_REQUIRED');self._verify(v)
  with self.store.tx() as db:
   current=self.cache._row(db,identity,'D_PREPARATION_V1')[0];require(current['state']=='PREPARED','D_SECOND_ATTEMPT_REFUSED')
   current['state']='COMMITTED';self.cache._put(db,'D_PREPARATION_V1',current,identity)
  claimed=False
  try:
   # Borne synthétique du superviseur de test existant, pas un tarif réel qualifié.
   self.budget.claim(identity,v['request'],900000)
   claimed=True
   e=v['gateway_entry_id']
   if e not in self.gateway.entries:
    # Reprise avant émission : reconstruction pure, identité durable conservée.
    fresh=self.gateway.prepare(v['resolved']);g=fresh['generation'];self.gateway.entries[e]=self.gateway.entries.pop(g['id']);self.gateway.entries[e].update(id=e,challenge=v['confirmation']['challenge'],confirmation=v['confirmation']['confirmation'])
   reply=self.gateway.confirm(v['confirmation'])
   current.update(state='COMPLETED' if reply.get('state')=='DISPLAYED' else 'UNKNOWN',reply=reply,directory=str(self.gateway.entries[e].get('directory') or ''))
   self.budget.finish(identity)
  except BaseException:
   current['state']='UNKNOWN' if claimed else 'BLOCKED'
   try:self.budget.finish(identity)
   except Exception:pass
   with self.store.tx() as db:self.cache._put(db,'D_PREPARATION_V1',current,identity)
   raise
  with self.store.tx() as db:self.cache._put(db,'D_PREPARATION_V1',current,identity)
  return reply
 def reconcile_sol_fixture(self,identity,receipt):
  v=self._read(identity);require(v['state'] in ('COMPLETED','UNKNOWN'),'D_NO_ATTEMPT')
  from .live_supervisor import LiveSupervisor
  s=LiveSupervisor(self.store.root/'d_runs'/v['gateway_entry_id']/'TEST_ONLY.sqlite',test=True);s.reconcile(receipt)
  state=s.snapshot();require(state['state']=='RECONCILED','D_UNSETTLED')
  self.budget.finish(identity,actual=state['actual_eur_micros'])
 def status(self,identity):
  v=self._read(identity);return {'state':v['state'],'reply':v.get('reply'),'retry_allowed':False,'historical_attempt':True,'budget_operation':self.budget.snapshot()['operations'].get(identity)}
