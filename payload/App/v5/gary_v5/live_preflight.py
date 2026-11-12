"""Prévol 3C uniquement : aucune émission, autorisation ou campagne commerciale.

Ce module pur ne lit ni coffre, ni préférences privées, ni registre historique.
Un dossier de préparation ne constitue jamais une permission de transport.
"""
import json
from .commercial_supervisor import fingerprint

VERSION = 'gary_v5_live_preflight_3c_v1'
MODEL = 'gpt-6.1-sol'
CEILING_EUR_MICROS = 1_000_000
TARGET = {'module': 'PATH', 'question': 'Hypercalcémie'}


def inspect_request(request):
    """Vérifie le corps exact existant ; ne remplace aucun paramètre en silence."""
    errors = []
    if type(request) is not dict:
        return ['REQUEST_INVALID']
    expected = {'model': MODEL, 'tools': [{'type': 'web_search', 'search_context_size': 'low'}],
                'max_tool_calls': 1, 'max_output_tokens': 2500, 'reasoning': {'effort': 'low'},
                'truncation': 'disabled', 'store': False, 'stream': False, 'background': False}
    for key, value in expected.items():
        if type(request.get(key)) is not type(value) or request[key] != value:
            errors.append('PARAMETER_INVALID_' + key.upper())
    allowed = set(expected) | {'instructions', 'input'}
    if set(request) != allowed:
        errors.append('UNREVIEWED_REQUEST_FIELDS')
    if not isinstance(request.get('instructions'), str) or not request['instructions'].strip():
        errors.append('INSTRUCTIONS_MISSING')
    try:
        data = json.loads(request.get('input', ''))
        if type(data) is not dict or any(data.get(k) != v for k, v in TARGET.items()):
            errors.append('TARGET_MISMATCH')
    except (ValueError, TypeError):
        errors.append('INPUT_INVALID')
    return errors


def preflight(request, *, now_ms, prepared_ms, expected_sha256, ceiling_eur_micros=CEILING_EUR_MICROS):
    """Diagnostic non émissible, sans donnée médicale ni corps dans le résultat.

    Les dates et SHA fournis servent à tester la fraîcheur, pas à prouver une
    autorisation humaine. Aucun dictionnaire navigateur de tarif n'est accepté.
    """
    errors = inspect_request(request)
    try:
        actual = fingerprint(request)
    except (ValueError, TypeError):
        actual = None
        errors.append('REQUEST_NOT_CANONICAL')
    if actual is None or actual != expected_sha256:
        errors.append('REQUEST_CHANGED')
    if (type(now_ms) is not int or type(prepared_ms) is not int
            or not 0 <= now_ms - prepared_ms <= 30_000):
        errors.append('PREPARATION_STALE')
    if type(ceiling_eur_micros) is not int or not 0 < ceiling_eur_micros <= CEILING_EUR_MICROS:
        errors.append('CEILING_INVALID')
    # Documentation publique != accès du projet. Aucune valeur client ne peut
    # lever ces blocages ; il faut une qualification et une autorisation séparées.
    blockers = ['PROJECT_MODEL_ACCESS_UNVERIFIED', 'BILLABLE_WEB_INPUT_BOUND_UNQUALIFIED',
                'EUR_ALL_IN_BOUND_UNQUALIFIED', 'NEW_LIVE_AUTHORIZATION_ABSENT',
                'LIVE_SUPERVISOR_NOT_CONNECTED', 'REAL_RENDER_EVIDENCE_NOT_QUALIFIED']
    return {'schema': VERSION, 'verdict': 'NO_GO', 'network_authorized': False,
            'transport_enabled': False, 'request_sha256': actual, 'errors': errors,
            'blockers': blockers, 'max_provider_calls': 1, 'ceiling_eur_micros': CEILING_EUR_MICROS,
            'commercial_reservation_eur_micros': None, 'expected_cost_eur_micros': None,
            'campaign_created': False, 'retry_allowed': False}


def emit(*args, **kwargs):
    """Verrou absolu, même avec une prétendue autorisation ou borne fictive."""
    raise PermissionError('PHASE_3C_TRANSPORT_SEALED')
