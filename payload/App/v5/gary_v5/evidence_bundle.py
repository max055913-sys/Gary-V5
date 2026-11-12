"""Preuves de restitution 3B : fixtures seulement, jamais un dossier LIVE."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from .commercial_supervisor import fingerprint, require

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_ROOTS = (ROOT/'data/evidence_tests', ROOT/'audits/phase_3B_preuves_TEST')
OMIT = {'authorization', 'api_key', 'secret', 'access_token', 'session_token', 'cookie', 'set-cookie',
        'request_headers', 'input', 'instructions', 'prompt', 'request', 'metadata'}


def _directory(directory):
    path = Path(directory).absolute()
    for p in (path, *path.parents):
        require(not p.is_symlink() and not p.is_junction(), 'EVIDENCE_PATH_REFUSED')
    require(any(path.resolve().is_relative_to(root.resolve()) and path.resolve() != root.resolve() for root in ALLOWED_ROOTS), 'TEST_EVIDENCE_PATH_REQUIRED')
    return path


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _save_manifest(directory, manifest):
    tmp = directory/'manifest.tmp'
    with tmp.open('x', encoding='utf8', newline='\n') as f:
        f.write(json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False))
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, directory/'manifest.json')


def create_fixture_bundle(directory, wrapper):
    require(isinstance(wrapper, dict) and wrapper.get('schema') == 'gary_v5_offline_generation_3b_v1'
            and wrapper.get('mode') == 'OFFLINE_ONLY' and wrapper.get('test') is True
            and wrapper.get('network_authorized') is False, 'LIVE_EVIDENCE_NOT_AUTHORIZED')
    response = wrapper.get('fixture_provider_response')
    require(isinstance(response, dict) and isinstance(response.get('output'), list), 'PROVIDER_EVIDENCE_INVALID')
    fragments = []
    for item in response['output']:
        if isinstance(item, dict) and item.get('type') == 'message':
            for part in item.get('content', []):
                if part.get('type') == 'output_text':
                    require(isinstance(part.get('text'), str), 'RAW_TEXT_INVALID')
                    fragments.append(part['text'])
    # Aucun séparateur n'est inventé. La segmentation originale reste dans JSON.
    text = ''.join(fragments)
    require(not re.search(r'\bsk-[A-Za-z0-9_-]{16,}', text), 'SENSITIVE_RAW_TEXT_EXPORT_REFUSED')
    omitted = []
    def sanitize(value, location=''):
        if isinstance(value, dict):
            result = {}
            for key, child in value.items():
                pointer = location + '/' + key
                if key.casefold() in OMIT:
                    omitted.append(pointer)
                else:
                    result[key] = sanitize(child, pointer)
            return result
        if isinstance(value, list):
            return [sanitize(child, location+'/'+str(i)) for i, child in enumerate(value)]
        return value
    cleaned = sanitize(response)
    raw = text.encode('utf8')  # Sans BOM, newline ajouté, normalisation ou correction.
    provider = json.dumps(cleaned, ensure_ascii=False, indent=2, allow_nan=False).encode('utf8')
    directory = _directory(directory)
    directory.mkdir(parents=True, exist_ok=False)
    manifest = {'schema': 'gary_test_evidence_3b_v1', 'state': 'PREPARE', 'test': True,
                'created_at_utc': datetime.now(timezone.utc).isoformat(), 'gary_version': 'V5-3B-OFFLINE',
                'provider_contacted': False, 'model_effectively_used': None,
                'model_declared_by_fixture': response.get('model'), 'provider_status': response.get('status'),
                'chain_status': wrapper.get('status'), 'provider_complete': response.get('status') == 'completed',
                'chain_complete': wrapper.get('status') == 'COMPLETE_TEST',
                'original_response_object_sha256': fingerprint(response), 'omitted_json_paths': omitted,
                'raw_text_fragment_count': len(fragments), 'raw_text_join': 'CONCATENATION_WITHOUT_ADDED_SEPARATOR',
                'files': {}, 'renderer_sources': {n: _sha(ROOT/n) for n in ['frontend/ResultCard.jsx', 'frontend/result-contract.mjs', 'frontend/shell.css']},
                'visual_fidelity': 'NOT_DEMONSTRATED', 'notes': ['TEST non médical, aucun appel fournisseur.']}
    _save_manifest(directory, manifest)
    for name, value in [('reponse_gary_brute.txt', raw), ('reponse_fournisseur.json', provider)]:
        with (directory/name).open('xb') as f:
            f.write(value)
            f.flush()
            os.fsync(f.fileno())
        manifest['files'][name] = _sha(directory/name)
    manifest['state'] = 'SOURCES_SAVED_RENDERING_PENDING'
    _save_manifest(directory, manifest)
    return manifest


def finalize_fixture_bundle(directory, pdf_name, captures, observation):
    directory = _directory(directory)
    manifest = json.loads((directory/'manifest.json').read_text('utf8'))
    require(manifest.get('test') is True and manifest['state'] == 'SOURCES_SAVED_RENDERING_PENDING', 'EVIDENCE_STATE_INVALID')
    require(all(_sha(directory/name) == sha for name, sha in manifest['files'].items()), 'ORIGINAL_EVIDENCE_CHANGED')
    require(captures and isinstance(observation, str) and observation.strip(), 'VISUAL_EVIDENCE_REQUIRED')
    for name in [pdf_name, *captures]:
        require(isinstance(name, str) and Path(name).name == name and (directory/name).is_file() and not (directory/name).is_symlink(), 'EVIDENCE_FILE_INVALID')
        manifest['files'][name] = _sha(directory/name)
    require((directory/pdf_name).read_bytes().startswith(b'%PDF-'), 'PDF_EVIDENCE_INVALID')
    require(all((directory/name).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for name in captures), 'CAPTURE_EVIDENCE_INVALID')
    for path in directory.iterdir():
        if path.is_file() and path.name != 'manifest.json':
            require(not path.is_symlink(), 'EVIDENCE_FILE_INVALID')
            manifest['files'][path.name] = _sha(path)
    manifest.update(state='TEST_BUNDLE_REVIEW_REQUIRED', visual_fidelity='CAPTURES_ARE_REFERENCE_NOT_PIXEL_CERTIFIED',
                    visual_observation=observation, human_validation=False)
    _save_manifest(directory, manifest)
    return manifest
