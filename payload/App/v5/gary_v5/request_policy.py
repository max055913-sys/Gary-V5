"""Validation applicative multimodule ; autorisation commerciale séparée.

Le prévol 3C garde sa cible historique. Cette politique ne donne aucun droit
d'émission et ne change ni modèle, ni prompts, ni limites techniques.
"""
import json
from .module_rules import RULES


def valid_application_request(request, *, standard=False,profile='legacy'):
    if profile in ('gary_sol_native_web_multi_v1','gary_sol_native_web_stream_v1','gary_sol_native_web_ttt_6000_v1','gary_sol_native_web_suivi_3500_v1'):
        from .sol_web_profile import validate
        return validate(request) and json.loads(request['input'])['documentary_web_profile']==profile
    if profile!='legacy':return False
    if type(request) is not dict:return False
    expected={'model':'gpt-6.1-sol','tools':[{'type':'web_search','search_context_size':'low'}],
              'max_tool_calls':1,'max_output_tokens':2500,'reasoning':{'effort':'low'},
              'store':False,'stream':False,'background':False,'truncation':'disabled'}
    if standard:expected['service_tier']='default'
    if set(request)!=set(expected)|{'instructions','input'}:return False
    if any(type(request.get(k)) is not type(v) or request[k]!=v for k,v in expected.items()):return False
    if type(request.get('instructions')) is not str or not request['instructions'].strip():return False
    try:
        data=json.loads(request['input'])
        return type(data) is dict and data.get('module') in RULES and type(data.get('question')) is str and bool(data['question'].strip()) and len(data['question'])<=1000
    except (ValueError,TypeError):return False
