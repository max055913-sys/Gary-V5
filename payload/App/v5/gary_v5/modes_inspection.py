"""Vue locale en lecture seule des instructions publiques réellement chargées.

Aucun appel Runtime, transport ou coffre ; aucune question utilisateur requise.
La sélection des fichiers est fixe, sans chemin fourni par le navigateur.
"""
import ast
from copy import deepcopy
from .sol_web_profile import parameters,apply as apply_web_profile
import hashlib
import inspect
import json
from .storage import ROOT
from .settings import Settings
from .functional_store import FunctionalStore
from .generation_contract import build_request,load_system_prompt,selected_conditions,DOCUMENTARY_INSTRUCTIONS,DEPTH_INSTRUCTIONS,CONTEXT_INSTRUCTIONS
from .module_rules import RULES,ROLES
from . import routing
from .live_supervisor import prepare_live_request
from .generation_gateway import GenerationGateway
from .semantic_contract import INSTRUCTIONS as SEMANTIC_INSTRUCTIONS,MODEL as LUNA_MODEL,VERSION as SEMANTIC_VERSION,SCHEMA as SEMANTIC_SCHEMA
from .semantic_cache import SEMANTIC_ENABLED,QUALIFIED_FOR_LIVE,SemanticCache


def sha(text):return hashlib.sha256(text.encode('utf8')).hexdigest()

def source(path,text=None):
    raw=path.read_bytes()
    effective=path.read_text('utf-8-sig') if text is None else text
    return {'path':str(path.relative_to(ROOT.parent)).replace('\\','/'),
            'file_sha256':hashlib.sha256(raw).hexdigest(),'text_sha256':sha(effective),'text':effective}


def inspection(store,module):
    if module not in routing.MODULES:raise ValueError('MODULE_INVALID')
    settings=Settings(store).read_write();context=FunctionalStore(store).options()['context_policy']
    # Patron sans question, sans profil ni préférence personnelle. Jamais envoyé.
    templates={m:build_request('',m,{},settings,context_policy=context) for m in RULES}
    fixed=[{k:v for k,v in t.items() if k not in ('instructions','input')} for t in templates.values()]
    if any(value!=fixed[0] for value in fixed):raise ValueError('MODULE_PARAMETERS_DIFFER')
    # Paramètres du transport Sol réellement sélectionné, sans émission.
    fixed[0]=parameters(module)
    common=source(ROOT/'prompts/systeme_medical.md',load_system_prompt())
    documentary=source(ROOT/'gary_v5/generation_contract.py',DOCUMENTARY_INSTRUCTIONS)
    instructions=[{'title':'Prompt médical commun','origin':'load_system_prompt()',**common},
                  {'title':'Instructions documentaires communes','origin':'build_request()',**source(ROOT/'prompts/transport_documentaire.md')},
                  {'title':'Profondeur, contexte et préférences documentaires','origin':'DOCUMENTARY_INSTRUCTIONS',**documentary}]
    instructions=[item for item in instructions if item['text'].strip()]
    defaults={m:{'depth':g['depth'],'priority_count':len(g['sources']),
                 'domain_count':len(g.get('preferred_domains',[])),
                 'secondary_automatic':g.get('secondary_automatic',True)} for m,g in settings['value']['modules'].items()}
    result={'schema':'gary_modes_inspection_v1','module':module,'modules':list(routing.MODULES),
            'read_only':True,'instructions':instructions,'fixed_parameters':fixed[0],
            'defaults':defaults,'context_default':context,
            'depth_instructions':DEPTH_INSTRUCTIONS,'context_instructions':CONTEXT_INSTRUCTIONS,
            'settings_revision':settings['value']['revision'],
            'conditional_selection':source(ROOT/'gary_v5/generation_contract.py',inspect.getsource(selected_conditions)),
            'conditional_preferences':dict(settings.get('conditional_preferences',{})),
            'parameters_source':source(ROOT/'gary_v5/sol_web_profile.py',inspect.getsource(parameters)),
            'adaptation_source':source(ROOT/'gary_v5/sol_web_profile.py',inspect.getsource(apply_web_profile)),
            'editable_in':{'depth':'Sources médicales ou sélecteur de recherche',
                           'context':'Configuration et sauvegardes',
                           'documentary_preferences':'Sources médicales'}}
    if module=='AUTO':
        # Référence fonctionnelle explicitement distinguée du code exécuté.
        specification=ROOT.parent/'Cahier_des_charges_Gary_V5.md'
        body=specification.read_text('utf-8-sig').split('### 3.1 AUTO',1)[1].split('### 3.2',1)[0]
        body=body.split('**Point technique',1)[0].strip()
        result.update(kind='routing',rules=[],routing_source=source(ROOT/'gary_v5/routing.py'),
                      routing_specification=source(specification,'### 3.1 AUTO '+body),assembled=None)
    else:
        rules=list(RULES[module]);joined='\n'.join(rules)
        result.update(kind='medical_contract',rules=rules,
                      rules_source=source(ROOT/'gary_v5/module_rules.py',joined),
                      assembled=source(ROOT/'gary_v5/generation_contract.py',templates[module]['instructions']))
        instructions.insert(2,{'title':'Contrat médical '+module,'origin':'RULES['+module+']',**result['rules_source']})
        active='Profondeur '+defaults[module]['depth']+' : '+DEPTH_INSTRUCTIONS[defaults[module]['depth']]+'\nContexte '+context+' : '+CONTEXT_INSTRUCTIONS[context]
        instructions.append({'title':'Instructions des modes actifs par défaut','origin':'build_request()',**source(ROOT/'gary_v5/generation_contract.py',active)})
    result['documentary_preferences']={m:json.loads(t['input']) for m,t in templates.items() if module=='AUTO' or m==module}
    result['preference_origin']=source(ROOT/'gary_v5/settings.py',inspect.getsource(Settings.read_write))
    result['request_conditionals']=source(ROOT/'gary_v5/generation_gateway.py',inspect.getsource(GenerationGateway.prepare_request))
    result['preparatory_semantic']={
        'version':SEMANTIC_VERSION,'model':LUNA_MODEL,'enabled':SEMANTIC_ENABLED,
        'qualified_for_live':QUALIFIED_FOR_LIVE,'production_connected':False,
        'roles':{m:ROLES[m] for m in RULES},
        'instructions':source(ROOT/'gary_v5/semantic_contract.py',SEMANTIC_INSTRUCTIONS),
        'output_schema':SEMANTIC_SCHEMA,
        'constructor':source(ROOT/'gary_v5/semantic_cache.py',inspect.getsource(SemanticCache._snapshot))}
    return result
