"""E1 : qualification documentaire et préflight fermé, aucun transport.

Références officielles examinées le 28 octobre 2026 ; accès du compte non vérifié.
Les calculs EUR des tests ne constituent jamais une autorisation commerciale.
"""
from decimal import Decimal,ROUND_CEILING
import json
from .commercial_supervisor import require
from .storage import digest
from .functional_store import privacy_check
from .semantic_contract import validate_decision
from .live_transport import strict_json

VERSION='gary_preflight_e1_v1'
DOC_DATE='2026-10-28'
MODELS={'gpt-6-luna':{'input':'0.10','output':'0.50','efforts':('none','low','medium','high','xhigh','max'),'output_cap':1024},
        'gpt-6.1-sol':{'input':'2.00','output':'10.00','efforts':('low','medium','high','xhigh','max'),'output_cap':2500}}
CONTEXT=1050000
SOURCES={k:'https://developers.openai.com/api/docs/models/'+k for k in MODELS}
SOURCES.update(pricing='https://developers.openai.com/api/docs/pricing',tokens='https://developers.openai.com/api/docs/guides/token-counting',
 structured='https://developers.openai.com/api/docs/guides/structured-outputs',caching='https://developers.openai.com/api/docs/guides/prompt-caching',
 web='https://developers.openai.com/api/docs/guides/tools-web-search',data='https://developers.openai.com/api/docs/guides/your-data',
 limits='https://developers.openai.com/api/docs/guides/spend-limits')

def strict_schema(schema,depth=0):
 require(type(schema) is dict and depth<=10,'E1_SCHEMA_UNSUPPORTED')
 t=schema.get('type')
 if t=='object':
  props=schema.get('properties');require(type(props) is dict and schema.get('additionalProperties') is False and set(schema.get('required',[]))==set(props),'E1_SCHEMA_NOT_STRICT')
  for value in props.values():strict_schema(value,depth+1)
 elif t=='array':strict_schema(schema.get('items'),depth+1)
 else:require(t in ('string','boolean','integer','number','null'),'E1_SCHEMA_UNSUPPORTED')

def assess(request):
 require(type(request) is dict and request.get('model') in MODELS,'E1_MODEL_NOT_QUALIFIED')
 allowed={'model','instructions','input','tools','max_tool_calls','text','max_output_tokens','reasoning','store','stream','background','truncation','service_tier','prompt_cache_options'}
 require(not set(request)-allowed,'E1_PARAMETER_NOT_QUALIFIED')
 require(type(request.get('input')) is str and type(request.get('instructions')) is str,'E1_TEXT_ONLY_REQUIRED');privacy_check(request)
 require(request.get('store') is False and request.get('stream') is False and request.get('background') is False and request.get('truncation')=='disabled','E1_PRIVACY_OR_TRUNCATION')
 require(request.get('service_tier')=='default','E1_SERVICE_TIER_NOT_QUALIFIED')
 model=MODELS[request['model']];out=request.get('max_output_tokens')
 require(type(out) is int and 16<=out<=model['output_cap'],'E1_OUTPUT_CAP')
 require(request.get('reasoning',{}).get('effort') in model['efforts'],'E1_REASONING_INCOMPATIBLE')
 cache=request.get('prompt_cache_options',{})
 require(type(cache) is dict and not set(cache)-{'mode','ttl'} and cache.get('mode','implicit') in ('implicit','explicit') and cache.get('ttl','30m') in ('30m','12h'),'E1_CACHE_OPTIONS')
 if request['model']=='gpt-6-luna':
  require(request.get('tools')==[],'E1_LUNA_TOOLS_FORBIDDEN')
  fmt=request.get('text',{}).get('format',{});require(fmt.get('type')=='json_schema' and fmt.get('strict') is True,'E1_LUNA_STRUCTURED_OUTPUT');strict_schema(fmt.get('schema'))
 tools=request.get('tools');require(type(tools) is list,'E1_TOOLS_INVALID')
 for tool in tools:
  require(type(tool) is dict and tool.get('type')=='web_search' and not set(tool)-{'type','search_context_size','return_token_budget'},'E1_TOOL_UNQUALIFIED')
  require(tool.get('search_context_size','medium') in ('low','medium','high') and tool.get('return_token_budget','default')=='default','E1_WEB_UNLIMITED_REFUSED')
 if tools:require(type(request.get('max_tool_calls')) is int and request['max_tool_calls']==1,'E1_WEB_CALL_CAP')
 # Pire cas d'une unique inférence texte SANS outil : fenêtre entière,
 # tranche longue, écriture cache 12h, majoration régionale et sortie raisonnement incluse.
 usd=((Decimal(CONTEXT)*Decimal(model['input'])*2*Decimal('2.5')+Decimal(out)*Decimal(model['output'])*Decimal('1.5'))/1000000)*Decimal('1.1')
 blockers=['ACCOUNT_ACCESS_NOT_VERIFIED','EUR_CONVERSION_TAX_FEES_NOT_QUALIFIED','E1_BIS_NOT_VALIDATED','NO_NEW_LIVE_AUTHORIZATION']
 if tools:blockers.insert(0,'WEB_BILLABLE_INPUT_BOUND_NOT_QUALIFIED')
 return {'schema':VERSION,'request_sha256':digest(request),'model':request['model'],'documentation_date':DOC_DATE,'model_access':'DOCUMENTED_NOT_ACCOUNT_TESTED',
         'provider_usd_bound':None if tools else str(usd),'bound_scope':'SINGLE_TEXT_RESPONSE_WITHOUT_TOOLS_FULL_CONTEXT_WORST_CASE',
         'real_input_token_count':None,'remote_count_cost':'UNQUALIFIED_NOT_ASSUMED_FREE','live_ready':False,'blockers':blockers,'sources':SOURCES}

def fixture_eur_bound(request,*,eur_per_usd='1',tax_factor='1.2',safety_factor='1.2'):
 report=assess(request);require(report['provider_usd_bound'] is not None,'E1_NO_DEFENSIBLE_WEB_BOUND')
 values=[Decimal(x) for x in (eur_per_usd,tax_factor,safety_factor)]
 require(all(x.is_finite() and x>0 for x in values) and values[1]>=1 and values[2]>=1,'E1_CONVERSION_INVALID')
 amount=(Decimal(report['provider_usd_bound'])*values[0]*values[1]*values[2]*1000000).to_integral_value(rounding=ROUND_CEILING)
 return {'kind':'E1_OFFLINE_BOUND','request_sha256':digest(request),'model':request['model'],'max_eur_micros':int(amount),'live_authorized':False,'assumptions':list(map(str,values))}

def decode_luna(raw,packet):
 response=strict_json(raw)
 require(type(response) is dict and response.get('status')=='completed' and response.get('model')=='gpt-6-luna','E1_RESPONSE_INCOMPLETE_OR_MODEL')
 output=response.get('output');require(type(output) is list and len(output)==1 and type(output[0]) is dict and output[0].get('type')=='message','E1_UNEXPECTED_LUNA_OUTPUT')
 content=output[0].get('content');require(type(content) is list and len(content)==1 and type(content[0]) is dict and content[0].get('type')=='output_text','E1_MODEL_REFUSAL_OR_OUTPUT')
 text=content[0].get('text');require(type(text) is str,'E1_RESPONSE_INVALID')
 decision=strict_json(text.encode('utf8'));validate_decision(decision,packet);return decision

def ui_preparation(question,module='AUTO'):
 # Contrat déjà compris par ResultCard ; aucune route ni génération activée.
 privacy_check({'question':question})
 return {'schema':'gary_v5_prepared_v1','status':'clarification','module':module,'question':question,
         'message':'Le nouveau workflow reste désactivé. Validation E1 et E1 bis, puis autorisation explicite requises avant tout appel.',
         'transport_enabled':False,'request_sha256':None}
