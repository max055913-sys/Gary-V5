"""Orchestration 3D : même automate en recette, transport HTTPS scellé."""
from copy import deepcopy
import hashlib
import json
import ssl
import urllib.request
import time
import socket
import threading
from .commercial_supervisor import require, canonical
from .live_supervisor import LiveSupervisor
from .generation_contract import display_result
from .live_evidence import save_response

# Aucune autorisation de cette phase ne permet de changer ce verrou.
NETWORK_RELEASE = None
TRUSTED_RELEASES = frozenset()


class ResponsesTransport:
    def exchange(self, supervisor, request):
        require(type(supervisor) is LiveSupervisor and not supervisor.test, 'REAL_TRANSPORT_TEST_REGISTRY_REFUSED')
        require(NETWORK_RELEASE is not None and NETWORK_RELEASE in TRUSTED_RELEASES, 'LIVE_NETWORK_SEALED')
        # Nouvelle vérification et engagement durable du compteur avant coffre/réseau.
        supervisor.mark_emission(request)
        from .windows_vault import Vault, protect
        from .live_supervisor import ROOT
        secret = bytearray(protect(Vault(ROOT/'data/private').path.read_bytes(), decrypt=True))
        try:
            require(secret.startswith(b'sk-') and not any(chr(c).isspace() for c in secret), 'CREDENTIAL_INVALID')
            start = time.perf_counter()
            try:
                return _https_once(request, secret)
            finally:
                self.https_ms = (time.perf_counter()-start)*1000
        finally:
            for i in range(len(secret)):
                secret[i] = 0


def _read_luna_body(response,deadline):
    """L'échéance couvre aussi les lectures internes du framing HTTP."""
    remaining=deadline-time.monotonic()
    if remaining<=0:raise TimeoutError('LUNA_READ_DEADLINE')
    sock=getattr(getattr(getattr(response,'fp',None),'raw',None),'_sock',None)
    def interrupt():
        try:sock.shutdown(socket.SHUT_RDWR)
        except OSError:pass
    timer=threading.Timer(remaining,interrupt) if sock is not None else None
    if timer:
        timer.daemon=True
        timer.start()
    try:
        data=response.read(8_388_609)
    except Exception:
        if time.monotonic()>=deadline:raise TimeoutError('LUNA_READ_DEADLINE') from None
        raise
    finally:
        if timer:timer.cancel()
    if time.monotonic()>=deadline:raise TimeoutError('LUNA_READ_DEADLINE')
    return data


def _https_once(request, secret, *, capture=None):
    """Une seule ouverture, aucun redirect/proxy/retry ; aucune journalisation."""
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *args, **kwargs):
            return None
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(),
                    urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    message = urllib.request.Request('https://api.openai.com/v1/responses',
            data=canonical(request).encode('utf8'),
            headers={'Authorization': 'Bearer '+secret.decode('ascii'), 'Content-Type': 'application/json'}, method='POST')
    from .sol_web_profile import transport_timeout
    timeout=transport_timeout(request)
    started=time.monotonic()
    with opener.open(message, timeout=timeout) as response:
        if request.get('stream') is True:
            from .responses_stream import StreamCapture
            capture=capture or StreamCapture(request['model'])
            require(response.headers.get_content_type()=='text/event-stream','SSE_CONTENT_TYPE')
            return capture.consume(response,deadline=started+timeout)
        data = _read_luna_body(response,started+timeout) if request.get('model')=='gpt-6-luna' else response.read(8_388_609)
        require(len(data) <= 8_388_608, 'PROVIDER_RESPONSE_TOO_LARGE')
        return data


class SimulatedTransport:
    """Uniquement registres de recette ; aucune donnée clinique fabriquée."""
    def __init__(self, scenario='complete', *, request_model_fixture=False):
        self.scenario = scenario
        self.calls = 0
        self.request_model_fixture=request_model_fixture

    def exchange(self, supervisor, request):
        require(supervisor.test, 'SIMULATION_IN_LIVE_REFUSED')
        supervisor.mark_emission(request); self.calls += 1
        if self.scenario == 'timeout':
            raise TimeoutError('INTERNAL_DO_NOT_LOG')
        if self.scenario == 'interrupt':
            raise KeyboardInterrupt()
        if self.scenario == 'error':
            raise RuntimeError('INTERNAL_DO_NOT_LOG')
        if self.scenario == 'invalid':
            return b'{invalid TEST}'
        response = {'id': 'TEST-RESPONSE', 'model': request['model'] if self.request_model_fixture else 'fixture-no-inference', 'status': 'completed',
                    'usage': {'input_tokens': 10, 'output_tokens': 20, 'total_tokens': 30},
                    'output': [{'type': 'message', 'content': [{'type': 'output_text',
                    'text': '# TEST technique\r\n\r\nTexte é e\u0301\r\n- élément\r\n| A | B |\r\n|---|---|\r\n| 1 | 2 |\r\n[Lien](https://example.org) [1]\r\nAVERTISSEMENT TEST.',
                    'annotations': [{'type': 'url_citation', 'url': 'https://example.org', 'title': 'TEST'}]}]}]}
        if self.scenario == 'incomplete':
            response.update(status='incomplete', incomplete_details={'reason': 'max_output_tokens'})
        if self.scenario == 'refusal':
            response['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'REFUS TEST'}]
        return json.dumps(response, ensure_ascii=False).encode('utf8')


def strict_json(raw):
    def pairs(items):
        result = {}
        for k, v in items:
            require(k not in result, 'DUPLICATE_JSON_KEY'); result[k] = v
        return result
    def reject(value):
        raise ValueError('NON_FINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=reject)


class LiveGeneration:
    def __init__(self, supervisor):
        require(type(supervisor) is LiveSupervisor, 'LIVE_SUPERVISOR_REQUIRED')
        self.supervisor = supervisor

    def checkpoint(self, stage):
        pass  # Point d'interruption des tests, jamais une option HTTP.

    def run(self, request, *, transport=None, evidence_directory):
        start = time.perf_counter()
        self.timings = {}
        s = self.supervisor
        transport = ResponsesTransport() if transport is None else transport
        require(type(transport) is (SimulatedTransport if s.test else ResponsesTransport), 'TRANSPORT_MODE_REFUSED')
        # Sans release serveur, aucune réservation de production n'est possible.
        if not s.test:
            require(NETWORK_RELEASE is not None and NETWORK_RELEASE in TRUSTED_RELEASES, 'LIVE_NETWORK_SEALED')
        current = deepcopy(request)
        s.reserve(current); self.checkpoint('reserved')
        s.engage(current); self.checkpoint('engaged')
        try:
            exchange_start = time.perf_counter()
            self.timings['prepare_to_transport_ms'] = (exchange_start-start)*1000
            raw = transport.exchange(s, current)
            self.timings['transport_exchange_ms'] = (time.perf_counter()-exchange_start)*1000
            self.timings['https_ms'] = getattr(transport, 'https_ms', None)
            self.checkpoint('emitted')
            require(type(raw) is bytes, 'PROVIDER_BYTES_REQUIRED')
            response = None
            try:
                response = strict_json(raw)
            except (ValueError, TypeError):
                pass
            # Sauvegarde avant toute validation/adaptation ; réponse incomplète conservée.
            evidence_start = time.perf_counter()
            bundle = save_response(evidence_directory, raw, response, s.snapshot())
            self.timings['evidence_ms'] = (time.perf_counter()-evidence_start)*1000
            result_sha = hashlib.sha256(raw).hexdigest()
            s.finish('RECEIVED' if isinstance(response, dict) else 'INVALID_JSON', result_sha)
            validation_start = time.perf_counter()
            try:
                result = display_result(current, response)
            except (ValueError, TypeError, AttributeError):
                result = None
            self.timings['validation_ms'] = (time.perf_counter()-validation_start)*1000
            self.timings['orchestration_ms'] = (time.perf_counter()-start)*1000
            return {'schema': 'gary_live_run_3d_v1', 'test': s.test, 'result': result,
                    'provider_status': response.get('status') if isinstance(response, dict) else 'INVALID_JSON',
                    'evidence_directory': str(bundle), 'cost_state': 'UNKNOWN', 'retry_allowed': False,
                    'timings': self.timings}
        except BaseException as exc:
            state = s.snapshot()['state']
            if state == 'ENGAGED':
                code = 'TIMEOUT' if isinstance(exc, TimeoutError) else 'INTERRUPTED' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'HTTP_ERROR'
                s.finish(code)
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            # Ne pas propager une exception fournisseur, des entêtes ou un secret.
            raise RuntimeError('LIVE_ATTEMPT_STOPPED_NO_RETRY') from None
