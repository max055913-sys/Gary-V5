"""Restitution fidèle par fragments et provenance native, sans téléchargement."""
from copy import deepcopy
import json
from urllib.parse import urlsplit
from .commercial_supervisor import require
from .functional_store import privacy_check

VERSION='gary_sol_web_result_v1'
def safe_url(value):
 try:
  u=urlsplit(value);return type(value) is str and u.scheme=='https' and bool(u.hostname) and not u.username and not u.password and u.port in (None,443) and not any(c.isspace() for c in value)
 except (ValueError,TypeError):return False
def display(request,response,*,test=False):
 require(type(response) is dict and response.get('model')==request['model'] and type(response.get('output')) is list,'SOL_WEB_PROVIDER_INVALID')
 body=json.loads(request['input']);fragments=[];actions=[];references=[];warnings=[];refusal=False
 require(len(response['output'])<=512,'SOL_WEB_OUTPUT_LIMIT')
 for item in response['output']:
  require(type(item) is dict,'SOL_WEB_PROVIDER_INVALID')
  if item.get('type')=='web_search_call':
   action=item.get('action');require(action is None or type(action) is dict,'SOL_WEB_ACTION_INVALID')
   actions.append({'id':item.get('id'),'status':item.get('status','unknown'),'action':deepcopy(action) if action else None})
  if item.get('type')!='message':continue
  for part in item.get('content',[]):
   if part.get('type')=='refusal':refusal=True
   if part.get('type')!='output_text':continue
   text=part.get('text');require(type(text) is str,'SOL_WEB_TEXT_INVALID');annotations=[]
   for a in part.get('annotations',[]):
    if type(a) is not dict or a.get('type')!='url_citation':continue
    original=deepcopy(a);start=a.get('start_index');end=a.get('end_index')
    valid=type(start) is int and type(end) is int and 0<=start<end<=len(text) and safe_url(a.get('url'))
    annotations.append({'original':original,'position_valid':valid,'citation_number':len(references)+1})
    if safe_url(a.get('url')):references.append({'url':a['url'],'title':a.get('title') if type(a.get('title')) is str else None,'fragment_index':len(fragments),'start_index':start,'end_index':end,'position_valid':valid,'origin':'SOL_NATIVE_WEB','full_document_read':None})
    if not valid:warnings.append('Position ou URL de citation non exploitable ; annotation originale conservée.')
   fragments.append({'text':text,'annotations':annotations,'message_id':item.get('id')})
 status=response.get('status','unknown');complete=status=='completed' and bool(fragments) and not refusal
 if response.get('incomplete_details',{} ) and response['incomplete_details'].get('reason')=='max_output_tokens':warnings.append(f"Limite de sortie atteinte : réponse tronquée (plafond {request.get('max_output_tokens', 'inconnu')} tokens).")
 if status!='completed':warnings.append('Réponse incomplète ou état inconnu. Aucun nouvel appel automatique.')
 if refusal:warnings.append('Refus du modèle.')
 value={'schema':VERSION,'module':body['module'],'question':body['question'],'test':test,'clinical_validation':False,
  'status':'complete' if complete else 'refusal' if refusal else 'partial' if fragments else 'technical_error','provider_status':status,
  'text':'\n'.join(f['text'] for f in fragments),'fragments':fragments,'references':references,'web_actions':actions,
  'usage':deepcopy(response.get('usage')),'service_tier':response.get('service_tier'),'warnings':warnings,
  'incomplete_details':deepcopy(response.get('incomplete_details')),'retry_allowed':False,
  'web_state':'received' if actions else 'not_observed','search_latency_ms':None,'consultation_latency_ms':None,'generation_latency_ms':None}
 # Horodatage réellement fourni, jamais remplacé par la date de consultation.
 created=response.get('created_at')
 if type(created) in (int,float) and 0<=created<=253402300799:value['provider_created_at']=created
 privacy_check(value);return value
