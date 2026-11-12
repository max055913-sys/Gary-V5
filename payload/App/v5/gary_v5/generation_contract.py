"""Préparation et validation pures, sans transport, coffre ou accès réseau."""
import json,re,unicodedata
from .storage import ROOT,digest
from .module_rules import RULES

DEPTH_INSTRUCTIONS={
 'rapide':'Réponse concise et directement exploitable : informations essentielles et alertes pertinentes. Ne jamais omettre une précaution critique au seul motif de brièveté.',
 'standard':'Réponse structurée couvrant les éléments habituellement nécessaires à la demande, avec un équilibre entre synthèse et détails.',
 'approfondie':'Couverture documentaire plus développée : arguments, nuances, conditions et exceptions utiles ; sources et limites davantage explicitées lorsqu’elles sont disponibles. Ne pas prétendre avoir consulté davantage de sources sans l’avoir fait.',
}

CONTEXT_INSTRUCTIONS={
 'court':'Exploiter de façon ciblée les informations utiles à la demande courante ; restitution compacte du contexte, sans perdre valeur, unité, négation, condition ou réserve nécessaire.',
 'intermediaire':'Relier les informations fournies aux populations et conditions pertinentes ; expliciter les dépendances utiles à la réponse, sans enrichir le profil par supposition.',
 'riche':'Développer les liens utiles entre les éléments du contexte fourni, les conditions et les limites d’applicabilité ; expliciter ce qui demeure inconnu, sans créer de données supplémentaires.',
}

DOCUMENTARY_INSTRUCTIONS='' # AUDIT-COMPACT-1 : bloc unique dans transport_documentaire.md

def selected_conditions(question,module,profile,settings):
 """Préférences intactes, non filtrées : leur pertinence est appréciée par Sol."""
 return [{'id':key,'preference':value,'activation_reason':'SOL_RELEVANCE_ASSESSMENT_REQUIRED'}
         for key,value in sorted(settings.get('conditional_preferences',{}).items()) if isinstance(value,str) and value.strip()]

def load_system_prompt():
 text=(ROOT/'prompts/systeme_medical.md').read_text(encoding='utf-8-sig')
 # Le fichier original conservé contient un ancien décodage UTF-8 en CP1252.
 # Réparation strictement réversible, limitée à ce prompt identifié ; aucun
 # changement du fichier original ni normalisation des contenus documentaires.
 if text.startswith('# MedicalGPT \u00e2\u20ac\u201d'):
  repaired=text.encode('cp1252').decode('utf8')
  if not repaired.startswith('# MedicalGPT — Instructions médicales v0.1') or repaired.encode('utf8').decode('cp1252')!=text:raise ValueError('SYSTEM_PROMPT_ENCODING_INVALID')
  return repaired
 return text

def build_request(question,module,profile,settings,depth=None,context_policy='intermediaire'):
 if module not in RULES:raise ValueError('MODULE_INVALID')
 group=settings['value']['modules'][module]
 depth=group['depth'] if depth is None else depth
 if depth not in ('rapide','standard','approfondie') or context_policy not in ('court','intermediaire','riche'):raise ValueError('PREPARATION_OPTIONS_INVALID')
 if group.get('secondary_automatic',True) is not True:raise ValueError('SECONDARY_POLICY_UNSUPPORTED')
 system=load_system_prompt()
 instructions=system.rstrip('\n')+'\n\n'+'\n'.join(RULES[module])+'\n\n'+(ROOT/'prompts/transport_documentaire.md').read_text('utf8').rstrip('\n')
 instructions+='\n\nProfondeur '+depth+' : '+DEPTH_INSTRUCTIONS[depth]+'\nContexte '+context_policy+' : '+CONTEXT_INSTRUCTIONS[context_policy]
 return {'model':'gpt-6.1-sol','instructions':instructions,'input':json.dumps({'question':question,'module':module,'profile':profile,'source_preferences':group['sources'],'preferred_domains':group.get('preferred_domains',[]),'secondary_automatic':group.get('secondary_automatic',True),'conditional_preferences':selected_conditions(question,module,profile,settings),'documentary_depth':depth,'context_policy':context_policy,'documentary_policy_version':'gary_v5_documentary_preferences_2c_v1','context_handling':{'scope':'CURRENT_REQUEST_ONLY','input_truncated':False,'external_memory':False,'token_budget_enforced':False}},ensure_ascii=False),
         'tools':[{'type':'web_search','search_context_size':'low'}],'max_tool_calls':1,'max_output_tokens':2500,
         'reasoning':{'effort':'low'},'store':False,'stream':False,'background':False,'truncation':'disabled'}

def validate_response(value):
 if not isinstance(value,dict) or value.get('status')!='completed':raise ValueError('RESPONSE_NOT_COMPLETED')
 text=[];references=[]
 for item in value.get('output',[]):
  if item.get('type')=='message':
   for part in item.get('content',[]):
    if part.get('type')=='refusal':raise ValueError('MODEL_REFUSAL')
    if part.get('type')=='output_text':
     text.append(part.get('text',''))
     for a in part.get('annotations',[]):
      if a.get('type')=='url_citation' and isinstance(a.get('url'),str) and a['url'].startswith('https://'):references.append({'url':a['url'],'title':a.get('title')})
 if not text or not ''.join(text).strip():raise ValueError('EMPTY_RESPONSE')
 return {'text':'\n'.join(text),'references':references,'clinical_validation':False}

def display_result(request,response):
 """Adaptation d'une réponse fournisseur, sans génération ni découpage clinique."""
 data=json.loads(request['input'])
 if data.get('module') not in RULES or not isinstance(data.get('question'),str):raise ValueError('RESULT_REQUEST_INVALID')
 return {'schema':'gary_v5_result_v1','module':data['module'],'question':data['question'],**validate_response(response)}
