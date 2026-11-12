"""Télémétrie technique à liste positive, aucun prompt, question ou secret."""
from decimal import Decimal
import re


def count(value):
    return value if type(value) is int and 0 <= value <= 10**12 else None


def metrics(response=None, timings=None, *, test=False):
    response = response if type(response) is dict else {}
    usage = response.get('usage') or {}
    if type(usage) is not dict:usage = {}
    def details(key):
        v = usage.get(key);return v if type(v) is dict else {}
    model = response.get('model')
    if type(model) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', model) or model.startswith('sk-'):model = None
    tier = response.get('service_tier') if response.get('service_tier') in ('default','auto','priority','flex','ultrafast') else None
    calls = [v for v in response.get('output', []) if type(v) is dict and v.get('type') == 'web_search_call'] if type(response.get('output', [])) is list else []
    known_web = all(type(v.get('action')) is dict and v['action'].get('type') in ('search','open_page','find_in_page') for v in calls)
    m = {'schema':'gary_generation_metrics_v1','test':test,'model_received':model,'service_tier_received':tier,
         'input_tokens':count(usage.get('input_tokens')),'output_tokens':count(usage.get('output_tokens')),
         'reasoning_tokens':count(details('output_tokens_details').get('reasoning_tokens')),
         'cached_tokens':count(details('input_tokens_details').get('cached_tokens')),
         'cache_write_tokens':count(details('input_tokens_details').get('cache_write_tokens')),
         'identified_web_search_calls':sum(v['action']['type']=='search' for v in calls) if known_web else None,
         'completeness':response.get('status') if response.get('status') in ('completed','incomplete','failed','cancelled') else 'unknown',
         'estimated_usd':None,'estimated_eur':None,'observed_calculated_usd':None,'observed_calculated_eur':None,
         'confirmed_eur':None,'fx_rate':None,'fx_date':None,'pricing_date':'2026-10-26',
         'pricing_source':'https://developers.openai.com/api/docs/pricing',
         'cost_note':'Calcul indicatif distinct de la facture et de la borne commerciale ; conversion non qualifiée.',
         'incomplete_reason':response.get('incomplete_details',{}).get('reason') if type(response.get('incomplete_details')) is dict and response['incomplete_details'].get('reason') in ('max_output_tokens','content_filter','stream_interrupted') else None,'timings_ms':{}}
    allowed = {'preparation_ms','prepare_to_transport_ms','transport_exchange_ms','https_ms','validation_ms','evidence_ms','orchestration_ms','server_run_ms'}
    for k,v in (timings or {}).items():
        if k in allowed and type(v) in (int,float) and 0 <= v <= 86_400_000:m['timings_ms'][k] = round(v,3)
    i,o,c,w = (m[k] for k in ('input_tokens','output_tokens','cached_tokens','cache_write_tokens'))
    # Ne calculer qu'avec une ventilation complète, un modèle/tier connus.
    if model=='gpt-6.1-sol' and tier=='default' and None not in (i,o,c,w,m['identified_web_search_calls']) and c+w <= i:
        multiplier = Decimal(2) if i>272000 else Decimal(1)
        # Tarif écriture retenu seulement quand aucun token d'écriture n'est présent : TTL non qualifié.
        if w==0:
            usd=(Decimal(i-c)*2+Decimal(c)*Decimal('.10'))*multiplier/1_000_000
            usd+=Decimal(o)*10*(Decimal('1.5') if i>272000 else 1)/1_000_000
            usd+=Decimal(m['identified_web_search_calls'])*Decimal('.01')
            m['observed_calculated_usd']=str(usd.quantize(Decimal('.00000001')))
    return m
