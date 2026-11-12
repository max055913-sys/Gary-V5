"""Profil Responses versionné, pur : aucune autorisation d'émission."""
from copy import deepcopy
import json
from .storage import digest,canonical
from .module_rules import RULES
from .functional_store import privacy_check
from .commercial_supervisor import require

LEGACY_VERSION='gary_sol_native_web_multi_v1'
VERSION='gary_sol_native_web_stream_v1'
TTT_VERSION='gary_sol_native_web_ttt_6000_v1'
SUIVI_VERSION='gary_sol_native_web_suivi_3500_v1'
PARAMETERS={'model':'gpt-6.1-sol','tools':[{'type':'web_search','search_context_size':'low'}],
 'tool_choice':'auto','max_tool_calls':12,'include':['web_search_call.action.sources'],
 'max_output_tokens':3000,'reasoning':{'effort':'low'},'service_tier':'default',
 'store':False,'stream':True,'background':False,'truncation':'disabled'}
LEGACY_PARAMETERS={**deepcopy(PARAMETERS),'stream':False,'max_output_tokens':2500}
def parameters(module=None):
 result=deepcopy(PARAMETERS)
 if module=='TTT':result['max_output_tokens']=6000
 if module=='SUIVI':result['max_output_tokens']=3500
 return result
def profile_version(module=None):return {'TTT':TTT_VERSION,'SUIVI':SUIVI_VERSION}.get(module,VERSION)
def profile_sha(*,streaming=True,module=None):
 if streaming and module=='TTT':return digest({'schema':TTT_VERSION,'parameters':parameters(module),'transport_timeout_seconds':120})
 if streaming and module=='SUIVI':return digest({'schema':SUIVI_VERSION,'parameters':parameters(module)})
 return digest({'schema':VERSION if streaming else LEGACY_VERSION,'parameters':PARAMETERS if streaming else LEGACY_PARAMETERS})
def transport_timeout(request):
 # Délai local, distinct de l’identité historique des profils et des caches.
 if validate(request) and request.get('stream') is True:return 180
 return 60
def validate(request):
 try:
  require(type(request) is dict and set(request)==set(PARAMETERS)|{'input','instructions'},'SOL_WEB_FIELDS')
  body=json.loads(request['input'])
  version=body.get('documentary_web_profile')
  module={TTT_VERSION:'TTT',SUIVI_VERSION:'SUIVI'}.get(version)
  require(not module or body.get('module')==module and request.get('stream') is True,'SOL_WEB_MODULE_SCOPE')
  params=parameters(module) if request.get('stream') is True else LEGACY_PARAMETERS
  require(all(type(request[k]) is type(v) and request[k]==v for k,v in params.items()),'SOL_WEB_PARAMETERS')
  require(type(request['instructions']) is str and bool(request['instructions'].strip()) and type(request['input']) is str,'SOL_WEB_TEXT')
  require(type(body) is dict and body.get('module') in RULES and type(body.get('question')) is str and 0<len(body['question'].strip())<=1000 and version==(profile_version(module) if request['stream'] else LEGACY_VERSION),'SOL_WEB_INPUT')
  privacy_check(request);return True
 except (ValueError,TypeError,KeyError,AttributeError):return False
def apply(request):
 from .request_policy import valid_application_request
 require(valid_application_request(request,standard='service_tier' in request),'SOL_WEB_BASE_INVALID')
 body=json.loads(request['input']);body['documentary_web_profile']=profile_version(body['module'])
 result={**parameters(body['module']),'instructions':request['instructions'],'input':canonical(body)}
 require(validate(result),'SOL_WEB_REQUEST_INVALID');return result
def preflight(request):
 require(validate(request),'SOL_WEB_REQUEST_INVALID')
 body=json.loads(request['input'])
 return {'schema':'gary_sol_web_preflight_v1','profile':body['documentary_web_profile'],'profile_sha256':request_profile_sha(request),'request_sha256':digest(request),'max_output_tokens':request['max_output_tokens'],'transport_timeout_seconds':transport_timeout(request),
  'documented_model_compatibility':True,'account_access_verified':False,'max_builtin_actions':12,'guaranteed_maximum_eur':None,
  'network_authorized':False,'expected_cost':None,'prudent_scenario':None,'needs_new_campaign_authorization':True}

def output_candidate(request,limit):
 """Proposition pure hors réseau : n'est ni un profil actif ni une autorisation.

 La sélection normale TTT est distincte ; ce comparateur ne modifie jamais
 les paramètres de production, les préférences ou les autorisations.
 """
 require(validate(request) and request.get('stream') is True,'SOL_WEB_REQUEST_INVALID')
 module=json.loads(request['input'])['module']
 require(type(limit) is int and limit in ((3000,6000,8000) if module=='TTT' else (3000,)),'SOL_OUTPUT_CANDIDATE_INVALID')
 candidate=deepcopy(request);candidate['max_output_tokens']=limit
 return {'schema':'gary_sol_output_candidate_v1','module':module,'candidate_request':candidate,
         'active_profile_accepts':validate(candidate),'production_limit':parameters(module)['max_output_tokens'],
         'network_authorized':False,'financially_qualified':False,'requires_owner_validation':True}

def request_profile_sha(request):
 require(validate(request), 'SOL_WEB_REQUEST_INVALID')
 body = json.loads(request['input'])
 module = body['module'] if body['documentary_web_profile'] in (TTT_VERSION,SUIVI_VERSION) else None
 return profile_sha(streaming=request['stream'], module=module)

def accepted_profiles():
 return {profile_sha(), profile_sha(module='TTT'), profile_sha(module='SUIVI'), profile_sha(streaming=False)}
