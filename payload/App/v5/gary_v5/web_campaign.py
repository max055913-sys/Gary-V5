"""Campagne Web v1 : journal SQLite durable, sans autorisation implicite."""
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
import json,sqlite3,time,re
from .storage import canonical,digest,ROOT
from .commercial_supervisor import require
from .sol_web_profile import validate, request_profile_sha, accepted_profiles
from .live_supervisor import TEST_ROOT
from .functional_store import privacy_check

VERSION='gary_sol_web_campaign_v1'
TRUSTED_AUTHORIZATIONS=frozenset()
TRUSTED_RECEIPTS=frozenset()

def daily(authorization):
 from .semantic_contract import daily_profile_sha
 return authorization['profile_sha256']==daily_profile_sha()
def valid_request(request):
 from .semantic_contract import validate_request
 return validate(request) or validate_request(request)
def matches(authorization,request):
 from .semantic_contract import validate_request
 return daily(authorization) and (validate_request(request) or validate(request) and request.get('stream') is True) or authorization['profile_sha256']==request_profile_sha(request)
def busy(authorization):return ('ENGAGED','EMITTING','UNCERTAIN') if daily(authorization) else ('ENGAGED','EMITTING','UNCERTAIN','RECEIVED_PENDING_COST')
def profiles():
 from .semantic_contract import daily_profile_sha
 return (*accepted_profiles(),daily_profile_sha())
def money(v):return type(v) is int and 0<=v<=10**12
def safe(path,test):
 p=Path(path).absolute();base=TEST_ROOT if test else ROOT/'data/web_campaigns'
 require(p.resolve().is_relative_to(base.resolve()),'WEB_CAMPAIGN_PATH')
 for a in (p,*p.parents):require(not a.is_symlink() and not a.is_junction(),'WEB_CAMPAIGN_PATH')
 return p

def check_authorization(authorization,test):
 privacy_check(authorization)
 require(type(authorization) is dict and set(authorization)=={'schema','test','campaign_id','envelope_eur_micros','max_requests','expires_at','profile_sha256','accepts_uncertain_current_cost','decision_reference'},'WEB_CAMPAIGN_AUTH_SCHEMA')
 require(authorization['schema']==VERSION and authorization['test'] is test and authorization['profile_sha256'] in profiles(),'WEB_CAMPAIGN_AUTH_SCOPE')
 require(type(authorization['campaign_id']) is str and re.fullmatch('[a-f0-9]{32}',authorization['campaign_id']) and type(authorization['decision_reference']) is str and 0<len(authorization['decision_reference'])<=100,'WEB_CAMPAIGN_AUTH_SCHEMA')
 require(money(authorization['envelope_eur_micros']) and authorization['envelope_eur_micros']>0 and type(authorization['max_requests']) is int and 0<authorization['max_requests']<=100 and type(authorization['expires_at']) in (int,float) and time.time()<authorization['expires_at']<time.time()+86400*30,'WEB_CAMPAIGN_AUTH_LIMITS')
 require(authorization['accepts_uncertain_current_cost'] is True,'WEB_CAMPAIGN_RISK_NOT_ACCEPTED')

class WebCampaign:
 def __init__(self,path,*,test=False,authority=None):
  require(type(test) is bool,'WEB_CAMPAIGN_MODE');self.path=safe(path,test);self.test=test;self.authority=authority
  if authority is not None:
   from .live_commissioning import OwnerRelease
   require(type(authority) is OwnerRelease and not test,'WEB_OWNER_AUTHORITY_REQUIRED')
 @classmethod
 def create(cls,path,authorization,*,test=False,authority=None):
  check_authorization(authorization,test)
  require(test or digest(authorization) in TRUSTED_AUTHORIZATIONS or authority is not None and authority.recognizes(authorization),'WEB_CAMPAIGN_NEW_AUTHORIZATION_REQUIRED')
  campaign=cls(path,test=test,authority=authority);campaign.path.parent.mkdir(parents=True,exist_ok=True)
  with campaign.tx() as db:
   db.execute('CREATE TABLE IF NOT EXISTS campaign(id INTEGER PRIMARY KEY CHECK(id=1),payload TEXT NOT NULL,sha TEXT NOT NULL)')
   db.execute('CREATE TABLE IF NOT EXISTS audit(sequence INTEGER PRIMARY KEY,payload TEXT NOT NULL,sha TEXT NOT NULL)')
   require(db.execute('SELECT 1 FROM campaign').fetchone() is None,'WEB_CAMPAIGN_ALREADY_EXISTS')
   campaign.save(db,{'schema':VERSION,'authorization':deepcopy(authorization),'state':'OPEN','operations':{}},'CREATED')
  return campaign
 @contextmanager
 def tx(self):
  safe(self.path,self.test);db=sqlite3.connect(self.path,timeout=5,isolation_level=None)
  try:db.execute('PRAGMA synchronous=FULL');db.execute('BEGIN IMMEDIATE');yield db;db.commit()
  except BaseException:db.rollback();raise
  finally:db.close()
 def load(self,db,*,active=False):
  row=db.execute('SELECT payload,sha FROM campaign WHERE id=1').fetchone();require(row is not None,'WEB_CAMPAIGN_ABSENT');v=json.loads(row[0]);require(digest(v)==row[1],'WEB_CAMPAIGN_CORRUPT')
  previous='0'*64;last=None
  for raw,h in db.execute('SELECT payload,sha FROM audit ORDER BY sequence'):
   event=json.loads(raw);require(digest(event)==h and event['previous']==previous,'WEB_CAMPAIGN_AUDIT_CORRUPT');previous=h;last=event
  require(last and last['state_sha256']==row[1] and v['authorization']['test'] is self.test,'WEB_CAMPAIGN_CORRUPT')
  require(self.test or digest(v['authorization']) in TRUSTED_AUTHORIZATIONS or self.authority is not None and self.authority.recognizes(v['authorization']),'WEB_CAMPAIGN_AUTHORIZATION_REVOKED')
  if active and self.authority is not None:require(self.authority.ready(),'WEB_CAMPAIGN_AUTHORIZATION_REVOKED')
  return v
 def save(self,db,v,event):
  row=db.execute('SELECT sha FROM audit ORDER BY sequence DESC LIMIT 1').fetchone();h=digest(v)
  entry={'event':event,'state_sha256':h,'previous':row[0] if row else '0'*64,'time':time.time()}
  db.execute('INSERT INTO audit(payload,sha) VALUES(?,?)',(canonical(entry),digest(entry)))
  db.execute('INSERT OR REPLACE INTO campaign VALUES(1,?,?)',(canonical(v),h))
 def snapshot(self):
  with self.tx() as db:v=self.load(db)
  return {**v,**self.totals(v),'guaranteed_maximum_current_call_eur':None}
 def totals(self,v):
  reconciled=sum(o['reconciled_eur_micros'] or 0 for o in v['operations'].values());observed=sum(o['observed_eur_micros'] or 0 for o in v['operations'].values())
  commitments=sum(max(o['planning_allocation_eur_micros'],o['observed_eur_micros'] or 0) for o in v['operations'].values() if o['state']!='RECONCILED')
  return {'observed_eur_micros':observed,'reconciled_eur_micros':reconciled,'commitments_eur_micros':commitments,'available_eur_micros':v['authorization']['envelope_eur_micros']-reconciled-commitments}
 def reserve(self,identity,request,*,allocation,expected=None,prudent=None,guaranteed=None,dependencies=None):
  require(type(identity) is str and re.fullmatch('[a-f0-9]{32}',identity) and valid_request(request),'WEB_CAMPAIGN_REQUEST')
  require(money(allocation) and allocation>0 and all(x is None or money(x) for x in (expected,prudent)) and guaranteed is None,'WEB_CAMPAIGN_PLANNING_INVALID')
  with self.tx() as db:
   v=self.load(db,active=True);a=v['authorization'];require(v['state']=='OPEN' and time.time()<a['expires_at'] and matches(a,request),'WEB_CAMPAIGN_CLOSED_OR_EXPIRED')
   require(identity not in v['operations'],'WEB_CAMPAIGN_SECOND_ATTEMPT_REFUSED');require(len(v['operations'])<a['max_requests'] and sum(x['emissions'] for x in v['operations'].values())<a['max_requests'],'WEB_CAMPAIGN_REQUEST_LIMIT')
   require(not any(o['state'] in busy(a) for o in v['operations'].values()),'WEB_CAMPAIGN_UNCERTAIN_COST')
   require(self.totals(v)['available_eur_micros']>=allocation,'WEB_CAMPAIGN_INSUFFICIENT_AVAILABLE')
   v['operations'][identity]={'state':'RESERVED','request_sha256':digest(request),'dependencies_sha256':dependencies,'planning_allocation_eur_micros':allocation,'expected_eur_micros':expected,'prudent_eur_micros':prudent,'guaranteed_eur_micros':None,'observed_eur_micros':None,'reconciled_eur_micros':None,'emissions':0}
   self.save(db,v,'RESERVED')
 def engage(self,identity,request,dependencies=None):
  with self.tx() as db:
   v=self.load(db,active=True);o=v['operations'][identity]
   require(v['state']=='OPEN' and time.time()<v['authorization']['expires_at'] and matches(v['authorization'],request),'WEB_CAMPAIGN_CLOSED_OR_EXPIRED')
   require(o['state']=='RESERVED' and o['request_sha256']==digest(request) and o['dependencies_sha256']==dependencies,'WEB_CAMPAIGN_CHANGED_OR_REPEATED')
   require(not any(x['state'] in busy(v['authorization']) for k,x in v['operations'].items() if k!=identity),'WEB_CAMPAIGN_UNCERTAIN_COST')
   o.update(state='ENGAGED');self.save(db,v,'ENGAGED_BEFORE_EMISSION')
 def claim_emission(self,identity,request):
  """Compteur consommé une fois, avant coffre et réseau, même en accès direct."""
  with self.tx() as db:
   v=self.load(db,active=True);o=v['operations'][identity]
   require(valid_request(request) and matches(v['authorization'],request),'WEB_CAMPAIGN_REQUEST')
   require(v['state']=='OPEN' and time.time()<v['authorization']['expires_at'],'WEB_CAMPAIGN_CLOSED_OR_EXPIRED')
   require(sum(x['emissions'] for x in v['operations'].values())<v['authorization']['max_requests'],'WEB_CAMPAIGN_REQUEST_LIMIT')
   require(not o.get('workflow'),'PROFESSIONAL_ACCESS_ARCHIVED')
   require(o['state']=='ENGAGED' and o['emissions']==0 and o['request_sha256']==digest(request),'WEB_CAMPAIGN_SECOND_EMISSION_REFUSED')
   o.update(state='EMITTING',emissions=1)
   self.save(db,v,'EMISSION_CLAIMED_DURABLY')
 def finish(self,identity,*,received=False,response_sha=None):
  with self.tx() as db:
   v=self.load(db);o=v['operations'][identity];require(o['state'] in ('ENGAGED','EMITTING'),'WEB_CAMPAIGN_FINISH_STATE')
   if received and o.get('workflow'):require(o['rounds'] and all(r['state']=='RECEIVED' for r in o['rounds']) and response_sha==o['rounds'][-1]['response_sha256'],'WEB_WORKFLOW_INCOMPLETE')
   o.update(state='RECEIVED_PENDING_COST' if received else 'UNCERTAIN',response_sha256=response_sha);self.save(db,v,o['state'])
 def record_usage(self,identity,usage):
  if type(usage) is not dict:return
  counts={k:usage[k] for k in ('input_tokens','output_tokens','total_tokens') if type(usage.get(k)) is int and 0<=usage[k]<=10**9}
  with self.tx() as db:
   v=self.load(db);o=v['operations'][identity];require(o['state']=='RECEIVED_PENDING_COST','WEB_USAGE_STATE');o['provider_usage']=counts;self.save(db,v,'PROVIDER_USAGE_NOT_INVOICE')
 def observe(self,identity,amount):
  require(self.test,'WEB_CAMPAIGN_OBSERVATION_PROOF_REQUIRED');require(money(amount),'WEB_CAMPAIGN_AMOUNT')
  with self.tx() as db:
   v=self.load(db);o=v['operations'][identity];require(o['state'] in ('RECEIVED_PENDING_COST','UNCERTAIN'),'WEB_CAMPAIGN_OBSERVATION_STATE')
   o.update(state='OBSERVED',observed_eur_micros=amount)
   if self.totals(v)['available_eur_micros']<0:v['state']='FROZEN'
   self.save(db,v,'OBSERVED_NOT_INVOICE')
 def reconcile(self,identity,receipt):
  privacy_check(receipt)
  require(type(receipt) is dict and set(receipt)=={'test','campaign_id','operation_id','request_sha256','amount_eur_micros','proof_reference'} and receipt['test'] is self.test and money(receipt['amount_eur_micros']) and type(receipt['proof_reference']) is str and 0<len(receipt['proof_reference'])<=100,'WEB_CAMPAIGN_RECEIPT_SCHEMA')
  require(self.test or digest(receipt) in TRUSTED_RECEIPTS or self.authority is not None and self.authority.recognizes_receipt(receipt),'WEB_CAMPAIGN_RECEIPT_NOT_RECOGNIZED')
  with self.tx() as db:
   v=self.load(db);o=v['operations'][identity];require(o['state'] in ('UNCERTAIN','RECEIVED_PENDING_COST','OBSERVED') and receipt['operation_id']==identity and receipt['campaign_id']==v['authorization']['campaign_id'] and receipt['request_sha256']==o['request_sha256'],'WEB_CAMPAIGN_RECEIPT_SCOPE')
   o.update(state='RECONCILED',reconciled_eur_micros=receipt['amount_eur_micros'],receipt_sha256=digest(receipt))
   if self.totals(v)['available_eur_micros']<0:v['state']='FROZEN'
   self.save(db,v,'RECONCILED')
 def revoke(self):
  with self.tx() as db:v=self.load(db);v['state']='REVOKED';self.save(db,v,'REVOKED')
 def recover_pending(self):
  """Action de reprise explicite : jamais une permission de réémettre."""
  with self.tx() as db:
   v=self.load(db)
   for o in v['operations'].values():
    if o['state'] in ('ENGAGED','EMITTING'):o['state']='UNCERTAIN'
   self.save(db,v,'RECOVERY_NO_RETRY')
