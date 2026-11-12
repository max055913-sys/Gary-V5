"""Conservation 3D distincte : texte exact, JSON expurgé, preuves visuelles reçues.

Ce module ne génère pas une nouvelle réponse et ne simule pas une facture.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from .commercial_supervisor import require
from .live_supervisor import ROOT, safe_path, TEST_ROOT
from .evidence_bundle import OMIT


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def directory(path, test):
    p = Path(path).absolute()
    root = TEST_ROOT if test else ROOT.parent.parent/'Data/live_3d/evidence'
    for part in (p, *p.parents):
        require(not part.is_symlink() and not part.is_junction(), 'EVIDENCE_REPARSE_REFUSED')
    require(p.resolve().is_relative_to(root.resolve()) and p.resolve() != root.resolve(), 'EVIDENCE_PATH_REFUSED')
    return p


def write(path, raw):
    with path.open('xb') as f:
        f.write(raw); f.flush(); os.fsync(f.fileno())


def manifest_write(path, value):
    temporary = path/'manifest.tmp'
    write(temporary, json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False).encode('utf8'))
    os.replace(temporary, path/'manifest.json')


def save_response(path, raw, response, state):
    require(state['state'] == 'ENGAGED' and state['emissions'] == 1, 'EVIDENCE_WITHOUT_ENGAGEMENT')
    p = directory(path, state['test'])
    # Un éventuel secret renvoyé doit bloquer l'export, pas être modifié en silence.
    require(not re.search(rb'\bsk-[A-Za-z0-9_-]{16,}', raw), 'SENSITIVE_PROVIDER_OUTPUT_REFUSED')
    from .functional_store import privacy_check
    privacy_check(response if isinstance(response,dict) else raw.decode('utf8',errors='replace'))
    p.mkdir(parents=True, exist_ok=False)
    m = {'schema': 'gary_live_evidence_3d_v1', 'test': state['test'], 'campaign': state['campaign'],
         'created_utc': datetime.now(timezone.utc).isoformat(), 'gary_version': 'V5-3D',
         'request_sha256': state['request_sha256'], 'response_bytes_sha256': sha(raw),
         'dependencies': state['dependencies'], 'state': 'PREPARE', 'files': {},
         'provider_complete': False, 'cost_eur_micros': None, 'cost_state': 'UNKNOWN',
         'visual_fidelity': 'NOT_CAPTURED', 'clinical_validation': False}
    manifest_write(p, m)
    omitted = []
    def clean(value, pointer=''):
        if isinstance(value, dict):
            out = {}
            for k, v in value.items():
                if k.casefold() in OMIT:
                    omitted.append(pointer+'/'+k)
                else:
                    out[k] = clean(v, pointer+'/'+k)
            return out
        if isinstance(value, list):
            return [clean(v, pointer+'/'+str(i)) for i, v in enumerate(value)]
        return value
    if isinstance(response, dict):
        texts = []
        for item in response.get('output', []):
            if isinstance(item, dict) and item.get('type') == 'message':
                for part in item.get('content', []):
                    if part.get('type') == 'output_text':
                        require(type(part.get('text')) is str, 'RAW_TEXT_INVALID')
                        texts.append(part['text'])
        sanitized = clean(response)
        files = {'reponse_gary_brute.txt': ''.join(texts).encode('utf8'),
                 'reponse_fournisseur.json': json.dumps(sanitized, ensure_ascii=False, indent=2).encode('utf8')}
        # Les octets HTTP originaux sont conservés seulement sans champ exclu.
        if not omitted:
            files['reponse_fournisseur_originale.json'] = raw
        m.update(provider_complete=response.get('status') == 'completed', provider_status=response.get('status'),
                 model_received=response.get('model'), usage=response.get('usage'),
                 service_tier=response.get('service_tier'), omitted_json_paths=omitted,
                 text_join='CONCATENATION_WITHOUT_ADDED_SEPARATOR')
    else:
        files = {'reponse_invalide.bin': raw}
        m['provider_status'] = 'INVALID_JSON'
    for name, content in files.items():
        write(p/name, content); m['files'][name] = sha(content)
    m['state'] = 'SOURCES_SAVED_VISUAL_PENDING'; manifest_write(p, m)
    return p


def attach_visual(path, *, test, pdf, captures, observation):
    p = directory(path, test)
    m = json.loads((p/'manifest.json').read_text('utf8'))
    require(m['test'] is test and m['state'] == 'SOURCES_SAVED_VISUAL_PENDING', 'EVIDENCE_STATE_REFUSED')
    require(all(sha((p/n).read_bytes()) == h for n, h in m['files'].items()), 'ORIGINAL_EVIDENCE_CHANGED')
    require(captures and type(observation) is dict and observation.get('dom_text_matches') is True,
            'VISUAL_OBSERVATION_REQUIRED')
    for n in [pdf, *captures]:
        require(type(n) is str and Path(n).name == n and not (p/n).is_symlink(), 'VISUAL_PATH_REFUSED')
        content = (p/n).read_bytes()
        require(content.startswith(b'%PDF-') if n == pdf else content.startswith(b'\x89PNG\r\n\x1a\n'), 'VISUAL_FORMAT_INVALID')
        m['files'][n] = sha(content)
    m.update(state='VISUAL_REVIEW_REQUIRED', visual_fidelity='CAPTURES_ARE_REFERENCE',
             visual_observation=observation, human_validation=False)
    manifest_write(p, m)
    return m


def attach_reconciliation(path, supervisor):
    state = supervisor.snapshot()
    require(state['state'] in {'RECONCILED', 'FROZEN'} and state.get('receipt') is not None,
            'COST_NOT_RECONCILED')
    p = directory(path, state['test'])
    m = json.loads((p/'manifest.json').read_text('utf8'))
    require(m['campaign'] == state['campaign'] and m['response_bytes_sha256'] == state['result_sha256'],
            'RECONCILIATION_BUNDLE_MISMATCH')
    require(all(sha((p/n).read_bytes()) == h for n, h in m['files'].items()), 'ORIGINAL_EVIDENCE_CHANGED')
    m.update(cost_eur_micros=state['actual_eur_micros'], cost_state=state['state'],
             consumption_receipt=state['receipt'])
    manifest_write(p, m)
    return m
