"""Supervision commerciale 3A : registre durable, exclusivement hors réseau.

Cette version accepte seulement des autorisations/preuves OFFLINE_FIXTURE.
Elle ne délivre JAMAIS une permission réseau. Une intégration réelle exigera
une frontière d'approbation humaine et une qualification tarifaire distinctes.
Montants : entiers en micro-euros (1 EUR = 1_000_000), jamais des flottants.
"""
from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import time
import uuid

TEST_ROOT = Path(__file__).resolve().parents[1] / 'data/commercial_supervisor_tests'
VERSION = 'gary_commercial_offline_3a_v1'
UNSETTLED = {'ENGAGED', 'UNCERTAIN'}
HELD = {'RESERVED', *UNSETTLED}
STATES = {*HELD, 'RECONCILED', 'CANCELLED'}
OUTCOMES = {'RECEIVED', 'PROVIDER_REFUSAL', 'TIMEOUT', 'INTERRUPTED', 'INCOMPLETE', 'HTTP_ERROR'}


class SupervisorError(ValueError):
    """Code fixe, sans contenu de requête ni exception fournisseur."""


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(value):
    return hashlib.sha256(canonical(value).encode('utf8')).hexdigest()


def require(condition, code):
    if not condition:
        raise SupervisorError(code)


def integer(value, minimum=0):
    return type(value) is int and minimum <= value <= 10**15


def sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


def identifier(value):
    return isinstance(value, str) and re.fullmatch('[A-Za-z0-9_-]{1,64}', value) is not None and not value.startswith('sk-')


def model_identifier(value):
    return isinstance(value, str) and re.fullmatch('[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', value) is not None and not value.startswith('sk-')


def _safe_path(path):
    p = Path(path).absolute()
    # Vérifier avant toute ouverture : jamais d'adoption d'une autre base.
    for part in (p, *p.parents):
        require(not part.is_symlink() and not part.is_junction(), 'REPARSE_POINT_REFUSED')
    require(p.resolve().is_relative_to(TEST_ROOT.resolve()) and p.suffix == '.sqlite', 'OFFLINE_PATH_REQUIRED')
    return p


class OfflineSupervisor:
    def __init__(self, path, clock=time.time):
        self.path = _safe_path(path)
        self.clock = clock
        require(self.path.is_file(), 'REGISTRY_ABSENT')
        # SQLite doit pouvoir annuler un journal laissé par un arrêt brutal.
        # Cette ouverture ne crée aucun schéma et refuse un état non reconnu.
        with self._db(write=True) as db:
            self._load(db)

    @classmethod
    def create(cls, path, clock=time.time):
        p = _safe_path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise SupervisorError('REGISTRY_ALREADY_EXISTS') from None
        os.close(fd)
        # Si interruption ici, le fichier incomplet reste refusé, jamais adopté.
        db = sqlite3.connect(p.as_uri() + '?mode=rw', uri=True, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            db.execute('CREATE TABLE registry(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)')
            db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY, code TEXT NOT NULL, state_sha TEXT NOT NULL, previous_sha TEXT NOT NULL, sha TEXT NOT NULL)')
            state = {'version': VERSION, 'mode': 'OFFLINE_ONLY', 'last_ms': 0, 'campaign': None, 'operations': {}}
            db.execute('INSERT INTO registry VALUES(1,?)', (canonical(state),))
            cls._event(db, state, 'CREATED')
            db.commit()
        finally:
            db.close()
        return cls(p, clock)

    @contextmanager
    def _db(self, write=False):
        path = _safe_path(self.path)
        db = sqlite3.connect(path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=10, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
            yield db
            if write:
                db.commit()
            else:
                db.rollback()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _event(db, state, code):
        last = db.execute('SELECT seq,sha FROM events ORDER BY seq DESC LIMIT 1').fetchone()
        seq, previous = (last[0] + 1, last[1]) if last else (1, '0' * 64)
        state_sha = fingerprint(state)
        h = fingerprint([seq, code, state_sha, previous])
        db.execute('INSERT INTO events VALUES(?,?,?,?,?)', (seq, code, state_sha, previous, h))

    @staticmethod
    def _load(db):
        try:
            require(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'REGISTRY_CORRUPT')
            state = json.loads(db.execute('SELECT payload FROM registry WHERE id=1').fetchone()[0])
            require(state['version'] == VERSION and state['mode'] == 'OFFLINE_ONLY', 'REGISTRY_VERSION_REFUSED')
            previous = '0' * 64
            events = db.execute('SELECT seq,code,state_sha,previous_sha,sha FROM events ORDER BY seq').fetchall()
            require(bool(events), 'AUDIT_CHAIN_ABSENT')
            for i, (seq, code, state_sha, prev, h) in enumerate(events, 1):
                require(seq == i and prev == previous and sha(state_sha) and h == fingerprint([seq, code, state_sha, prev]), 'AUDIT_CHAIN_CORRUPT')
                previous = h
            require(events[-1][2] == fingerprint(state), 'REGISTRY_STATE_DIVERGENT')
            require(all(op['state'] in STATES for op in state['operations'].values()), 'OPERATION_STATE_INVALID')
            return state
        except (sqlite3.DatabaseError, KeyError, TypeError, AttributeError, json.JSONDecodeError):
            raise SupervisorError('REGISTRY_CORRUPT') from None

    def _change(self, code, function):
        with self._db(write=True) as db:
            state = self._load(db)
            now = int(self.clock() * 1000)
            require(now >= state['last_ms'], 'CLOCK_ROLLBACK_REFUSED')
            original = deepcopy(state)
            error = None
            try:
                result = function(state, now)
            except SupervisorError as exc:
                state = original  # Même une fonction partiellement exécutée ne publie rien.
                error = exc
                code = 'REFUSED_' + str(exc)
            state['last_ms'] = now
            db.execute('UPDATE registry SET payload=? WHERE id=1', (canonical(state),))
            self._event(db, state, code)
        if error is not None:
            raise error
        return deepcopy(result)

    @staticmethod
    def _active(state, now):
        c = state['campaign']
        require(c is not None, 'CAMPAIGN_ABSENT')
        require(c['status'] == 'AUTHORIZED', 'CAMPAIGN_NOT_ACTIVE')
        require(now < c['spec']['expires_ms'], 'CAMPAIGN_EXPIRED')
        return c

    @staticmethod
    def _balance(state):
        ops = list(state['operations'].values())
        spent = sum(op['actual_eur_micros'] for op in ops if op['state'] == 'RECONCILED')
        held = sum(op['reserved_eur_micros'] for op in ops if op['state'] in HELD)
        budget = state['campaign']['spec']['budget_eur_micros'] if state['campaign'] else 0
        return {'authorized_eur_micros': budget, 'known_eur_micros': spent, 'held_eur_micros': held,
                'available_eur_micros': budget - spent - held,
                'calls_committed': sum(op['state'] != 'CANCELLED' for op in ops),
                'uncertain_operations': sum(op['state'] in UNSETTLED for op in ops)}

    @staticmethod
    def _fresh(campaign, request, prepared_ms, now):
        spec = campaign['spec']
        require(isinstance(request, dict) and request.get('model') == spec['model'], 'MODEL_MISMATCH')
        require(fingerprint(request) == spec['request_sha256'], 'REQUEST_SCOPE_MISMATCH')
        require(integer(prepared_ms) and 0 <= now - prepared_ms <= spec['max_age_ms'], 'REQUEST_STALE')

    @staticmethod
    def _bound(bound, request, now):
        require(isinstance(bound, dict) and set(bound) == {'kind', 'qualified', 'currency', 'request_sha256', 'model', 'max_eur_micros', 'expires_ms', 'evidence_sha256'}, 'BOUND_INVALID')
        require(bound['kind'] == 'OFFLINE_FIXTURE' and bound['qualified'] is True, 'BOUND_UNQUALIFIED')
        require(bound['currency'] == 'EUR', 'CURRENCY_UNQUALIFIED')
        require(bound['request_sha256'] == fingerprint(request) and bound['model'] == request['model'], 'BOUND_SCOPE_MISMATCH')
        require(integer(bound['expires_ms']) and now < bound['expires_ms'], 'BOUND_EXPIRED')
        require(integer(bound['max_eur_micros'], 1) and sha(bound['evidence_sha256']), 'BOUND_INVALID')

    def draft(self, spec):
        def apply(s, now):
            require(s['campaign'] is None, 'CAMPAIGN_ALREADY_EXISTS')
            require(isinstance(spec, dict) and set(spec) == {'id', 'model', 'request_sha256', 'max_calls', 'budget_eur_micros', 'expires_ms', 'max_age_ms'}, 'CAMPAIGN_SPEC_INVALID')
            require(identifier(spec['id']) and spec['id'] != 'V5-LIVE-01' and model_identifier(spec['model']), 'CAMPAIGN_ID_INVALID')
            require(sha(spec['request_sha256']) and integer(spec['max_calls'], 1) and integer(spec['budget_eur_micros'], 1), 'CAMPAIGN_LIMIT_INVALID')
            require(integer(spec['expires_ms']) and now < spec['expires_ms'] and integer(spec['max_age_ms'], 1), 'CAMPAIGN_EXPIRY_INVALID')
            s['campaign'] = {'spec': deepcopy(spec), 'status': 'DRAFT', 'created_ms': now, 'authorization': None}
            return s['campaign']
        return self._change('DRAFT_CREATED', apply)

    def register_preparation(self, request_sha256, model, dependency_sha256):
        """Identité et date créées ici, jamais reprises d'un formulaire."""
        def apply(s, now):
            require(sha(request_sha256) and sha(dependency_sha256) and model_identifier(model), 'PREPARATION_INVALID')
            prepared = {'id': 'prep_' + uuid.uuid4().hex, 'created_ms': now,
                        'request_sha256': request_sha256, 'model': model,
                        'dependency_sha256': dependency_sha256, 'mode': 'OFFLINE_ONLY'}
            s.setdefault('preparations', {})[prepared['id']] = prepared
            return prepared
        return self._change('PREPARATION_REGISTERED', apply)

    def bind_preparation_fixture(self, preparation_id):
        def apply(s, now):
            prepared = s.get('preparations', {}).get(preparation_id)
            c = s['campaign']
            require(prepared is not None, 'PREPARATION_ABSENT')
            require(c is not None and c['status'] == 'DRAFT', 'CAMPAIGN_BINDING_REFUSED')
            require(c['spec']['request_sha256'] == prepared['request_sha256'] and c['spec']['model'] == prepared['model'], 'PREPARATION_SCOPE_MISMATCH')
            require(c.get('preparation_id', preparation_id) == preparation_id, 'CAMPAIGN_BINDING_REFUSED')
            c['preparation_id'] = preparation_id
            return {'preparation_id': preparation_id, 'network_authorized': False}
        return self._change('FIXTURE_PREPARATION_BOUND', apply)

    def authorize_fixture(self, spec_sha256, decision_sha256):
        """Uniquement un accord fictif, jamais une nouvelle autorisation payante."""
        def apply(s, now):
            c = s['campaign']
            require(c is not None and c['status'] == 'DRAFT', 'AUTHORIZATION_NOT_AVAILABLE')
            require(sha(decision_sha256) and spec_sha256 == fingerprint(c['spec']), 'AUTHORIZATION_SCOPE_MISMATCH')
            require(now < c['spec']['expires_ms'], 'CAMPAIGN_EXPIRED')
            c['status'] = 'AUTHORIZED'
            c['authorization'] = {'kind': 'OFFLINE_FIXTURE', 'decision_sha256': decision_sha256, 'spec_sha256': spec_sha256, 'approved_ms': now}
            return {'state': 'AUTHORIZED', 'network_authorized': False}
        return self._change('FIXTURE_AUTHORIZED', apply)

    def revoke(self):
        def apply(s, now):
            require(s['campaign'] is not None, 'CAMPAIGN_ABSENT')
            s['campaign']['status'] = 'REVOKED'
            s['campaign']['revoked_ms'] = now
            return {'state': 'REVOKED'}
        return self._change('REVOKED', apply)

    def reserve(self, operation_id, request, prepared_ms, bound):
        def apply(s, now):
            c = self._active(s, now)
            require(identifier(operation_id), 'OPERATION_ID_INVALID')
            self._fresh(c, request, prepared_ms, now)
            self._bound(bound, request, now)
            ops = s['operations']
            old = ops.get(operation_id)
            if old:
                require(old['request_sha256'] == fingerprint(request) and old['prepared_ms'] == prepared_ms and old['bound'] == bound, 'OPERATION_CONFLICT')
                return old  # Une répétition n'accorde pas une nouvelle émission.
            # Même préparation, autre identifiant de clic : même opération canonique.
            for op in ops.values():
                if op['request_sha256'] == fingerprint(request) and op['prepared_ms'] == prepared_ms:
                    require(op['bound'] == bound, 'OPERATION_CONFLICT')
                    return op
            balance = self._balance(s)
            require(balance['uncertain_operations'] == 0, 'UNRECONCILED_COST_BLOCKS_NEW_START')
            require(balance['calls_committed'] < c['spec']['max_calls'], 'CALL_LIMIT_REACHED')
            require(bound['max_eur_micros'] <= balance['available_eur_micros'], 'BUDGET_INSUFFICIENT')
            op = {'id': operation_id, 'request_sha256': fingerprint(request), 'prepared_ms': prepared_ms,
                  'bound': deepcopy(bound), 'reserved_eur_micros': bound['max_eur_micros'],
                  'actual_eur_micros': None, 'state': 'RESERVED', 'outcome': None,
                  'result_sha256': None, 'reserved_ms': now}
            ops[operation_id] = op
            return op
        return self._change('RESERVED', apply)

    def engage_fixture(self, operation_id, request):
        """Transition avant émission simulée. Aucun permis utilisable par send."""
        def apply(s, now):
            c = self._active(s, now)
            op = s['operations'].get(operation_id)
            require(op is not None and op['state'] == 'RESERVED', 'OPERATION_ALREADY_ENGAGED_OR_UNAVAILABLE')
            self._fresh(c, request, op['prepared_ms'], now)
            self._bound(op['bound'], request, now)
            require(self._balance(s)['uncertain_operations'] == 0, 'UNRECONCILED_COST_BLOCKS_NEW_START')
            op.update(state='ENGAGED', engaged_ms=now)
            return {'operation_id': operation_id, 'state': 'ENGAGED', 'network_authorized': False, 'simulated': True}
        return self._change('FIXTURE_ENGAGED', apply)

    def cancel_unengaged(self, operation_id):
        def apply(s, now):
            op = s['operations'].get(operation_id)
            require(op is not None and op['state'] in {'RESERVED', 'CANCELLED'}, 'ENGAGED_RESERVATION_CANNOT_BE_RELEASED')
            op.update(state='CANCELLED', cancelled_ms=now)
            return op
        return self._change('CANCELLED_BEFORE_ENGAGEMENT', apply)

    def outcome(self, operation_id, outcome, result_sha256=None):
        def apply(s, now):
            require(outcome in OUTCOMES, 'OUTCOME_INVALID')
            require(result_sha256 is None or sha(result_sha256), 'RESULT_FINGERPRINT_INVALID')
            op = s['operations'].get(operation_id)
            require(op is not None and op['state'] in UNSETTLED, 'OUTCOME_STATE_INVALID')
            require(op['outcome'] in (None, outcome), 'OUTCOME_CONFLICT')
            require(op['result_sha256'] in (None, result_sha256), 'RESULT_FINGERPRINT_CONFLICT')
            op.update(state='UNCERTAIN', outcome=outcome, result_sha256=result_sha256, outcome_ms=now)
            return op
        return self._change('OUTCOME_COST_UNRECONCILED', apply)

    def recover(self):
        def apply(s, now):
            count = 0
            for op in s['operations'].values():
                if op['state'] == 'ENGAGED':
                    op.update(state='UNCERTAIN', outcome='INTERRUPTED', outcome_ms=now)
                    count += 1
            return {'uncertain_operations_added': count}
        return self._change('RECOVERY_NO_RETRY', apply)

    def reconcile_fixture(self, operation_id, receipt):
        def apply(s, now):
            require(isinstance(receipt, dict) and set(receipt) == {'kind', 'qualified', 'currency', 'amount_eur_micros', 'evidence_sha256'}, 'RECEIPT_INVALID')
            require(receipt['kind'] == 'OFFLINE_FIXTURE' and receipt['qualified'] is True and receipt['currency'] == 'EUR', 'COST_UNQUALIFIED')
            require(integer(receipt['amount_eur_micros']) and sha(receipt['evidence_sha256']), 'RECEIPT_INVALID')
            op = s['operations'].get(operation_id)
            require(op is not None and op['state'] in {*UNSETTLED, 'RECONCILED'}, 'RECONCILIATION_STATE_INVALID')
            if op['state'] == 'RECONCILED':
                require(op['receipt'] == receipt, 'RECONCILIATION_CONFLICT')
                return op
            op.update(state='RECONCILED', actual_eur_micros=receipt['amount_eur_micros'], receipt=deepcopy(receipt), reconciled_ms=now)
            if op['actual_eur_micros'] > op['reserved_eur_micros'] or self._balance(s)['available_eur_micros'] < 0:
                s['campaign']['status'] = 'FROZEN'  # Enregistrer un dépassement, ne pas le cacher.
            return op
        return self._change('COST_RECONCILED_FIXTURE', apply)

    def snapshot(self):
        with self._db() as db:
            state = self._load(db)
            result = deepcopy(state)
            result['balance'] = self._balance(state)
            c = state['campaign']
            result['effective_campaign_state'] = ('EXPIRED' if c and c['status'] == 'AUTHORIZED' and int(self.clock()*1000) >= c['spec']['expires_ms'] else c['status'] if c else 'ABSENT')
            result['network_authorized'] = False
            return result
