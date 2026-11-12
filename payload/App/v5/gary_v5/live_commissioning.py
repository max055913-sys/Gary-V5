"""Mise en service locale explicite. Aucune autorisation créée au démarrage.

Le sceau DPAPI reconnaît une décision du propriétaire, pas une disponibilité
fournisseur ni une garantie du coût courant. Aucun secret API n'est consulté.
"""
import hashlib,json,re,sqlite3,time
from pathlib import Path
from .storage import ROOT,canonical,digest
from .commercial_supervisor import require
from .windows_vault import protect,atomic_bytes

SCHEMA='gary_owner_live_release_v1'
ACK='AUTORISER CETTE CAMPAGNE ET SON RISQUE DE COUT NON GARANTI'

def implementation():
 from .sol_web_gateway import dependencies
 paths=[Path(__file__),ROOT/'server.py',ROOT/'scripts/commission_live.py',ROOT/'gary_v5/windows_vault.py',ROOT/'gary_v5/live_transport.py',ROOT/'gary_v5/generation_gateway.py']
 return digest({'gateway':dependencies(),'commissioning':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}})

REQUEST_SCOPE='gary_live_request_scope_v1'

def approved_request_sha(request):
 return digest({'schema':REQUEST_SCOPE,'request':{**request,'input':json.loads(request['input'])}})

def has_request_scope(plan):
 return plan.get('request_scope')==REQUEST_SCOPE and re.fullmatch('[0-9a-f]{64}',str(plan.get('approved_request_sha256',''))) is not None

class OwnerRelease:
 def __init__(self):self.path=ROOT/'data/private/live_release.dpapi'
 def read(self,*,active=True):
  for p in (self.path,*self.path.parents):require(not p.is_symlink() and not p.is_junction(),'LIVE_RELEASE_PATH')
  require(self.path.is_file() and self.path.stat().st_size<=65536,'LIVE_RELEASE_ABSENT')
  v=json.loads(protect(self.path.read_bytes(),decrypt=True))
  require(v['schema']==SCHEMA and v['state'] in ('APPROVED','REVOKED'),'LIVE_RELEASE_INVALID')
  a=v['plan']['authorization'];require(a['test'] is False,'LIVE_RELEASE_INVALID')
  if active:
   require(v['state']=='APPROVED','LIVE_RELEASE_REVOKED')
   require(v['plan'].get('scope')=='DAILY' or has_request_scope(v['plan']),'LIVE_REQUEST_SCOPE_REQUIRED')
   require(v['implementation_sha256']==implementation(),'LIVE_RELEASE_CODE_CHANGED')
   require(time.time()<a['expires_at'],'LIVE_RELEASE_EXPIRED')
  return v
 def recognizes(self,authorization):return digest(self.read(active=False)['plan']['authorization'])==digest(authorization)
 def recognizes_receipt(self,receipt):return digest(receipt) in self.read(active=False)['receipts']
 def ready(self):
  try:self.read();return True
  except (ValueError,KeyError,TypeError,OSError):return False
 def check(self,request,campaign,operation_id=None):
  from .sol_web_profile import validate
  from .semantic_contract import validate_request as luna_request
  v=self.read();plan=v['plan'];is_luna=luna_request(request);daily=plan.get('scope')=='DAILY'
  require(validate(request) or daily and is_luna,'LIVE_PUBLIC_PROFILE_ONLY')
  allocation=plan['luna_allocation_eur_micros'] if is_luna else plan['allocation_eur_micros']
  state=campaign.snapshot()
  require(campaign.authority is self and self.recognizes(state['authorization']),'LIVE_RELEASE_CAMPAIGN')
  require(state['state']=='OPEN','LIVE_CAMPAIGN_CLOSED')
  require(not any(o['state'] in (('ENGAGED','EMITTING','UNCERTAIN') if daily else ('ENGAGED','EMITTING','UNCERTAIN','RECEIVED_PENDING_COST')) for k,o in state['operations'].items() if k!=operation_id),'WEB_CAMPAIGN_UNCERTAIN_COST')
  if operation_id is None:
   require(len(state['operations'])<state['authorization']['max_requests'] and state['available_eur_micros']>=allocation,'LIVE_CAMPAIGN_EXHAUSTED')
  else:
   require(state['operations'][operation_id]['planning_allocation_eur_micros']==allocation,'LIVE_ALLOCATION_CHANGED')
  b=json.loads(request['input'])
  if daily:
   require(is_luna or b['module'] in plan['modules'],'LIVE_MODULE_NOT_AUTHORIZED')
  else:
   require(b['module']==plan['module'] and digest(b['question'])==plan['question_sha256'],'LIVE_RELEASE_QUESTION_SCOPE')
   require(approved_request_sha(request)==plan['approved_request_sha256'],'LIVE_APPROVED_REQUEST_CHANGED')
  require(campaign.path.resolve()==self.campaign_path(plan).resolve(),'LIVE_RELEASE_CAMPAIGN_PATH')
 def campaign_path(self,plan):return ROOT/'data/web_campaigns'/('owner_'+plan['authorization']['campaign_id']+'.sqlite')
 def seal(self,v):atomic_bytes(self.path,protect(canonical(v).encode()))
 def approve(self,plan,confirmation):
  from .sol_web_profile import profile_sha
  from .semantic_contract import MODULES,daily_profile_sha
  from .web_campaign import WebCampaign,money,check_authorization
  require(confirmation==ACK+' '+digest(plan),'LIVE_OWNER_CONFIRMATION_REQUIRED')
  daily=type(plan) is dict and plan.get('scope')=='DAILY'
  if daily:
   require(set(plan)=={'authorization','allocation_eur_micros','luna_allocation_eur_micros','modules','scope','qualification_reference'},'LIVE_PLAN_SCHEMA')
   require(type(plan['modules']) is list and plan['modules']==list(MODULES),'LIVE_PLAN_SCOPE')
   require(money(plan['luna_allocation_eur_micros']) and plan['luna_allocation_eur_micros']>0,'LIVE_LUNA_ALLOCATION')
  else:
   require(type(plan) is dict and set(plan)=={'authorization','allocation_eur_micros','module','question_sha256','qualification_reference','request_scope','approved_request_sha256'},'LIVE_PLAN_SCHEMA')
   require(has_request_scope(plan),'LIVE_REQUEST_SCOPE_REQUIRED')
   require(plan['module'] in MODULES and type(plan['question_sha256']) is str and len(plan['question_sha256'])==64,'LIVE_PLAN_SCOPE')
  require(type(plan['qualification_reference']) is str and 0<len(plan['qualification_reference'])<=200,'LIVE_QUALIFICATION_REQUIRED')
  a=plan['authorization'];require(a['test'] is False and a['profile_sha256']==(daily_profile_sha() if daily else profile_sha(module=plan['module'])),'LIVE_PUBLIC_PROFILE_ONLY')
  require(money(plan['allocation_eur_micros']) and 0<plan['allocation_eur_micros']<=a['envelope_eur_micros'],'LIVE_ALLOCATION')
  check_authorization(a,False)
  require(daily or a['max_requests']==1,'LIVE_DRAFT_LIMITS')
  if daily:require(plan['allocation_eur_micros']+plan['luna_allocation_eur_micros']<=a['envelope_eur_micros'],'LIVE_WORKFLOW_ALLOCATION')
  history=[]
  if self.path.exists():
   previous=self.read(active=False)
   expired=time.time()>=previous['plan']['authorization']['expires_at']
   require(expired or previous['state']=='REVOKED','LIVE_RELEASE_ALREADY_EXISTS_REVOKE_FIRST')
   old=WebCampaign(self.campaign_path(previous['plan']),authority=self).snapshot()
   # Une dette non rapprochée reste une dette : seule une autorisation expirée
   # peut être remplacée sans règlement, sans toucher à son registre.
   require(expired or all(o['state']=='RECONCILED' for o in old['operations'].values()),'LIVE_PREVIOUS_COST_UNSETTLED')
   require(a['campaign_id']!=old['authorization']['campaign_id'],'LIVE_CAMPAIGN_REUSE_REFUSED')
   history=list(previous.get('previous_campaigns',[]))
   require(a['campaign_id'] not in {h['campaign_id'] for h in history},'LIVE_CAMPAIGN_REUSE_REFUSED')
   require(not self.campaign_path(plan).exists(),'WEB_CAMPAIGN_ALREADY_EXISTS')
   archive=self.campaign_path(previous['plan']).with_suffix('.release.dpapi')
   require(not archive.exists(),'LIVE_PREVIOUS_PROOF_ALREADY_EXISTS');atomic_bytes(archive,self.path.read_bytes())
   history.append({'campaign_id':old['authorization']['campaign_id'],'expired_at_replacement':expired,
    'ledger':self.campaign_path(previous['plan']).name,'ledger_sha256':hashlib.sha256(self.campaign_path(previous['plan']).read_bytes()).hexdigest(),
    'release_archive':archive.name,'reconciled_eur_micros':old['reconciled_eur_micros'],
    'unsettled_commitments_eur_micros':old['commitments_eur_micros'],
    'unsettled_operations':{k:o['state'] for k,o in old['operations'].items() if o['state']!='RECONCILED'}})
  require(not self.campaign_path(plan).exists(),'WEB_CAMPAIGN_ALREADY_EXISTS')
  self.seal({'schema':SCHEMA,'state':'APPROVED','created_at':time.time(),'implementation_sha256':implementation(),'plan':plan,'receipts':[], 'previous_campaigns':history})
  try:return WebCampaign.create(self.campaign_path(plan),a,authority=self)
  except BaseException:
   self.revoke();raise
 def revoke(self):
  # Ne supprime ni le registre, ni son historique, ni une autorisation consommée.
  if not self.path.exists():return
  v=self.read(active=False);v.update(state='REVOKED',revoked_at=time.time());self.seal(v)
 def reconcile(self,identity,receipt,confirmation):
  from .web_campaign import WebCampaign
  require(confirmation=='RECONCILIER '+digest(receipt),'LIVE_RECEIPT_CONFIRMATION_REQUIRED')
  v=self.read(active=False);require(receipt['campaign_id']==v['plan']['authorization']['campaign_id'],'LIVE_RECEIPT_SCOPE')
  v['receipts'].append(digest(receipt));self.seal(v)
  WebCampaign(self.campaign_path(v['plan']),authority=self).reconcile(identity,receipt)

def attach(gateway):
 """Uniquement l'instance de production ; aucune clé ni requête à l'ouverture."""
 from .web_campaign import WebCampaign
 from .sol_web_gateway import CampaignResponsesTransport
 require(gateway.runtime.store.root==(ROOT/'data').resolve(),'LIVE_PRODUCTION_STORE_REQUIRED')
 release=OwnerRelease()
 if not release.path.exists():return
 try:
  v=release.read();campaign=WebCampaign(release.campaign_path(v['plan']),authority=release)
  require(campaign.path.is_file(),'LIVE_CAMPAIGN_ABSENT');state=campaign.snapshot()
  require(state['state']=='OPEN','LIVE_CAMPAIGN_CLOSED')
  gateway.campaign=campaign;gateway.allocation=v['plan']['allocation_eur_micros'];gateway.transport=CampaignResponsesTransport(release=release)
  if v['plan'].get('scope')=='DAILY':gateway.luna.configure_live(campaign,gateway.transport,v['plan']['luna_allocation_eur_micros'])
 except (ValueError,KeyError,TypeError,OSError,sqlite3.Error):
  gateway.commissioning_blocker='Autorisation locale absente, révoquée, périmée ou incompatible. Transport fermé.'
