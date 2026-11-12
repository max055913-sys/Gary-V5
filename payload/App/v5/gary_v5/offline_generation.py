"""Raccordement 3B uniquement OFFLINE : aucun client réseau, aucune route HTTP."""
from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import re

from .application import Runtime
from .commercial_supervisor import OfflineSupervisor, SupervisorError, fingerprint, require, integer
from .generation_contract import display_result

ROOT = Path(__file__).resolve().parents[1]
INPUT_KEYS = {'query', 'module', 'profile', 'privacy_confirmed', 'depth', 'context_policy', 'model'}


@dataclass(frozen=True)
class FixtureDecision:
    preparation_id: str
    request_sha256: str
    model: str
    max_calls: int
    budget_eur_micros: int
    expires_ms: int
    max_age_ms: int
    decision_sha256: str
    approved: bool = False
    kind: str = 'OFFLINE_FIXTURE'


@dataclass(frozen=True)
class FixturePacket:
    response: object
    receipt: object
    outcome: str


class FixtureTransport:
    """Transport fini déterministe. Il n'accepte ni URL, ni callback réseau."""
    SCENARIOS = {'success', 'long', 'timeout', 'error', 'interrupt', 'refusal', 'incomplete', 'malformed', 'unknown_cost', 'unqualified_cost', 'reconciliation_refused'}

    def __init__(self, scenario='success', amount_eur_micros=100):
        require(scenario in self.SCENARIOS and integer(amount_eur_micros), 'FIXTURE_TRANSPORT_INVALID')
        self.scenario = scenario
        self.amount_eur_micros = amount_eur_micros
        self.calls = 0

    def exchange(self, request):
        require(self.scenario in FixtureTransport.SCENARIOS and integer(self.amount_eur_micros), 'FIXTURE_TRANSPORT_INVALID')
        self.calls += 1
        if self.scenario == 'timeout':
            raise TimeoutError('FICTIONAL_TIMEOUT')
        if self.scenario == 'error':
            raise RuntimeError('FIXTURE_INTERNAL_DETAILS_NOT_TO_LOG')
        if self.scenario == 'interrupt':
            raise KeyboardInterrupt()
        text = '# TITRE TEST\n\nParagraphe technique accentué : é è à œ.\n\n- Élément A\n- Élément B\n\n| Colonne A | Colonne B |\n|---|---|\n| Valeur 1 | Valeur 2 |\n\n[Lien technique](https://example.org) [1]\n\nAVERTISSEMENT TEST : aucune information médicale.'
        if self.scenario == 'long':
            text += ''.join('\n\n## BLOC TEST '+str(i).zfill(2)+'\nParagraphe de pagination : caractères accentués, condition technique, liste et réserve conservées sans correction.' for i in range(1, 25))
            text += '\n\nFIN EXACTE TEST — avertissement final conservé.'
        response = {'id': 'fixture_response', 'model': request['model'], 'status': 'completed',
                    'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': text, 'annotations': []}]}]}
        outcome = 'RECEIVED'
        if self.scenario == 'refusal':
            response['output'][0]['content'] = [{'type': 'refusal', 'refusal': 'REFUS TECHNIQUE TEST'}]
            outcome = 'PROVIDER_REFUSAL'
        if self.scenario == 'incomplete':
            response['status'] = 'incomplete'
            response['incomplete_details'] = {'reason': 'fixture_limit'}
            outcome = 'INCOMPLETE'
        if self.scenario == 'malformed':
            response = {'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'output_text', 'text': 42}]}]}
        receipt = {'kind': 'OFFLINE_FIXTURE', 'qualified': True, 'currency': 'EUR',
                   'amount_eur_micros': self.amount_eur_micros,
                   'evidence_sha256': fingerprint(['fixture_receipt', fingerprint(request), self.scenario, self.amount_eur_micros])}
        if self.scenario in {'unknown_cost', 'incomplete', 'refusal'}:
            receipt = None
        if self.scenario == 'unqualified_cost':
            receipt['qualified'] = False
        if self.scenario == 'reconciliation_refused':
            receipt['currency'] = 'USD'
        return FixturePacket(response, receipt, outcome)


class OfflineGeneration:
    def __init__(self, runtime, supervisor, mode='OFFLINE_ONLY'):
        require(mode == 'OFFLINE_ONLY', 'LIVE_UNAVAILABLE')
        require(type(runtime) is Runtime and type(supervisor) is OfflineSupervisor, 'OFFLINE_COMPONENT_REQUIRED')
        require(supervisor.snapshot()['mode'] == 'OFFLINE_ONLY', 'OFFLINE_COMPONENT_REQUIRED')
        self.runtime = runtime
        self.supervisor = supervisor

    @staticmethod
    def _dependencies():
        names = ['prompts/systeme_medical.md', 'prompts/transport_documentaire.md',
                 'gary_v5/module_rules.py', 'gary_v5/generation_contract.py', 'gary_v5/routing.py',
                 'gary_v5/settings.py', 'gary_v5/settings_support.py', 'config/priorities.p3.json']
        return fingerprint({n: hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in names})

    def _request(self, data):
        require(isinstance(data, dict) and not set(data) - INPUT_KEYS, 'UNTRUSTED_PREPARATION_FIELDS')
        before = self._dependencies()
        summary, request = self.runtime.prepare_request(data)
        require(summary['status'] == 'prepared' and isinstance(request, dict), 'PREPARATION_NEEDS_CLARIFICATION')
        require(request.get('store') is False and request.get('background') is False and request.get('stream') is False, 'REQUEST_SAFETY_INVALID')
        require(before == self._dependencies(), 'PREPARATION_DEPENDENCIES_CHANGED')
        return json.loads(json.dumps(request, ensure_ascii=False, allow_nan=False)), before

    def prepare(self, data):
        request, dependencies = self._request(data)
        return self.supervisor.register_preparation(fingerprint(request), request['model'], dependencies)

    def _prepared(self, preparation_id):
        prepared = self.supervisor.snapshot().get('preparations', {}).get(preparation_id)
        require(prepared is not None, 'PREPARATION_ABSENT')
        return prepared

    def authorize_fixture(self, decision):
        require(type(decision) is FixtureDecision and decision.kind == 'OFFLINE_FIXTURE' and decision.approved is True, 'FIXTURE_NOT_APPROVED')
        prepared = self._prepared(decision.preparation_id)
        require(decision.request_sha256 == prepared['request_sha256'] and decision.model == prepared['model'], 'AUTHORIZATION_SCOPE_MISMATCH')
        spec = {'id': 'fixture_' + prepared['id'], 'model': decision.model, 'request_sha256': decision.request_sha256,
                'max_calls': decision.max_calls, 'budget_eur_micros': decision.budget_eur_micros,
                'expires_ms': decision.expires_ms, 'max_age_ms': decision.max_age_ms}
        self.supervisor.draft(spec)
        self.supervisor.bind_preparation_fixture(prepared['id'])
        return self.supervisor.authorize_fixture(fingerprint(spec), decision.decision_sha256)

    @staticmethod
    def _reply(status, operation_id, code=None, result=None, provider_response=None):
        reply = {'schema': 'gary_v5_offline_generation_3b_v1', 'mode': 'OFFLINE_ONLY', 'test': True,
                'label': 'TEST HORS RÉSEAU — aucune réponse médicale validée', 'status': status,
                'operation_id': operation_id, 'code': code, 'result': result, 'network_authorized': False}
        if provider_response is not None:
            reply['fixture_provider_response'] = provider_response
        return reply

    def _checkpoint(self, stage):
        """Point de test interne, jamais exposé à HTTP et sans effet par défaut."""

    def cancel(self, preparation_id):
        self._prepared(preparation_id)
        return self.supervisor.cancel_unengaged(preparation_id)

    def recover(self):
        return self.supervisor.recover()  # Aucun appel de transport pendant la reprise.

    def run(self, preparation_id, data, transport, bound):
        stage = 'PREPARATION'
        engaged = False
        response_for_evidence = None
        try:
            require(type(transport) is FixtureTransport, 'REAL_TRANSPORT_REFUSED')
            prepared = self._prepared(preparation_id)
            request, dependencies = self._request(data)
            require(fingerprint(request) == prepared['request_sha256'] and dependencies == prepared['dependency_sha256'], 'PREPARED_REQUEST_CHANGED')
            stage = 'AUTHORIZATION'
            campaign = self.supervisor.snapshot()['campaign']
            require(campaign is not None and campaign.get('preparation_id') == preparation_id, 'AUTHORIZATION_ABSENT')
            stage = 'RESERVATION'
            operation = self.supervisor.reserve(preparation_id, request, prepared['created_ms'], bound)
            if operation['state'] != 'RESERVED':
                return self._reply('ALREADY_PROCESSED' if operation['state'] == 'RECONCILED' else operation['state'], preparation_id)
            self._checkpoint('reserved')
            stage = 'ENGAGEMENT'
            current, current_dependencies = self._request(data)
            require(fingerprint(current) == prepared['request_sha256'] and current_dependencies == prepared['dependency_sha256'], 'PREPARED_REQUEST_CHANGED')
            grant = self.supervisor.engage_fixture(preparation_id, current)
            require(grant['network_authorized'] is False, 'OFFLINE_BOUNDARY_INVALID')
            engaged = True
            self._checkpoint('engaged')
            require(self.supervisor.snapshot()['operations'][preparation_id]['state'] == 'ENGAGED', 'ENGAGEMENT_STATE_CHANGED')
            stage = 'TRANSPORT'
            # Appel de la classe admise, pas d'une fonction arbitraire d'instance.
            packet = FixtureTransport.exchange(transport, current)
            require(type(packet) is FixturePacket, 'FIXTURE_PACKET_INVALID')
            response_for_evidence = packet.response
            stage = 'OUTCOME'
            self.supervisor.outcome(preparation_id, packet.outcome, fingerprint(packet.response))
            stage = 'RECONCILIATION'
            if packet.receipt is None:
                return self._reply(packet.outcome if packet.outcome != 'RECEIVED' else 'COST_UNKNOWN', preparation_id, 'COST_UNRECONCILED', provider_response=response_for_evidence)
            self.supervisor.reconcile_fixture(preparation_id, packet.receipt)
            require(self.supervisor.snapshot()['campaign']['status'] != 'FROZEN', 'COST_BOUND_EXCEEDED')
            stage = 'VALIDATION'
            result = display_result(current, packet.response)
            result.update(schema='gary_v5_test_result_3b_v1', simulation=True, test=True)
            return self._reply('COMPLETE_TEST', preparation_id, result=result, provider_response=response_for_evidence)
        except BaseException as exc:
            if engaged:
                try:
                    op = self.supervisor.snapshot()['operations'][preparation_id]
                    if op['state'] in {'ENGAGED', 'UNCERTAIN'} and op['outcome'] is None:
                        self.supervisor.outcome(preparation_id, 'TIMEOUT' if isinstance(exc, TimeoutError) else 'INTERRUPTED' if isinstance(exc, (KeyboardInterrupt, SystemExit)) else 'HTTP_ERROR')
                except Exception:
                    pass  # L'engagement durable reste bloquant même si cet audit échoue.
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            code = str(exc) if isinstance(exc, (SupervisorError, ValueError)) and re.fullmatch('[A-Z][A-Z0-9_]{1,90}', str(exc)) else 'OFFLINE_OPERATION_FAILED'
            status = 'TIMEOUT' if isinstance(exc, TimeoutError) else 'INVALID_RESPONSE' if stage == 'VALIDATION' else stage + '_REFUSED'
            return self._reply(status, preparation_id, code, provider_response=response_for_evidence)
