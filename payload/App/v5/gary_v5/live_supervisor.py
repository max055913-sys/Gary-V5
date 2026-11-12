"""Registre 3D distinct : un corps, une opération, aucun retry.

Les empreintes de décisions reconnues sont une liste de confiance côté code,
vide en production. Le navigateur n'a aucune route permettant de la remplir.
Ce contrôle n'est pas une défense contre la modification du code par son propriétaire.
"""
from contextlib import contextmanager
from copy import deepcopy
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid
from .commercial_supervisor import canonical, fingerprint, require, integer
from .live_preflight import inspect_request
from .request_policy import valid_application_request

ROOT = Path(__file__).resolve().parents[1]
TEST_ROOT = ROOT/'data/live_3d_tests'
LIVE_PATH = ROOT/'data/live_3d/campaign.sqlite'
TRUSTED_APPROVALS = frozenset()
TRUSTED_BOUNDS = frozenset()
TRUSTED_RECEIPTS = frozenset()
VERSION = 'gary_live_supervisor_3d_v1_1'


def prepare_live_request(request):
    """Adaptation explicite 3D : Standard fixé, corps/SHA différents de 3C.

    Aucun changement de modèle, prompt, outil ou plafond. Ne pas utiliser
    l'ancien SHA pour autoriser ce nouveau corps.
    """
    require(valid_application_request(request), 'REQUEST_INVALID')
    return {**deepcopy(request), 'service_tier': 'default'}


def valid_request(request):
    return valid_application_request(request, standard=True)


def safe_path(path, test):
    p = Path(path).absolute()
    for part in (p, *p.parents):
        require(not part.is_symlink() and not part.is_junction(), 'REPARSE_REFUSED')
    allowed_live=p==LIVE_PATH or (p.parent==LIVE_PATH.parent/'campaigns' and __import__('re').fullmatch(r'[0-9a-f]{32}\.sqlite',p.name) is not None)
    require((p.resolve().is_relative_to(TEST_ROOT.resolve()) and p.suffix == '.sqlite')
            if test else allowed_live, 'REGISTRY_PATH_REFUSED')
    return p


class LiveSupervisor:
    def __init__(self, path=LIVE_PATH, *, test=False, clock=time.time):
        self.test = test is True
        self.path = safe_path(path, self.test)
        self.clock = clock
        require(self.path.is_file(), 'REGISTRY_ABSENT')
        with self.db() as db:
            self.load(db)

    @classmethod
    def create(cls, request, path=LIVE_PATH, *, test=False, clock=time.time):
        require(valid_request(request), 'REQUEST_INVALID')
        p = safe_path(path, test)
        p.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600); os.close(fd)
        state = {'version': VERSION, 'test': test is True, 'campaign': 'V5-3D-'+uuid.uuid4().hex,
                 'request_sha256': fingerprint(request), 'prepared_ms': int(clock()*1000),
                 'dependencies': dependencies(), 'state': 'DRAFT', 'last_ms': 0,
                 'approval': None, 'bound': None, 'actual_eur_micros': None,
                 'emissions': 0, 'result_sha256': None}
        db = sqlite3.connect(p)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('CREATE TABLE registry(payload TEXT NOT NULL, sha TEXT NOT NULL)')
            db.execute('CREATE TABLE events(seq INTEGER PRIMARY KEY, code TEXT, sha TEXT, previous TEXT)')
            db.execute('INSERT INTO registry VALUES(?,?)', (canonical(state), fingerprint(state)))
            code = canonical({'code': 'CREATED', 'state_sha': fingerprint(state)})
            db.execute('INSERT INTO events VALUES(1,?,?,?)', (code, fingerprint([1, code, '0'*64]), '0'*64))
            db.commit()
        finally:
            db.close()
        return cls(p, test=test, clock=clock)

    @contextmanager
    def db(self):
        p = safe_path(self.path, self.test)
        db = sqlite3.connect(p.as_uri()+'?mode=rw', uri=True, timeout=10, isolation_level=None)
        try:
            db.execute('PRAGMA synchronous=FULL'); db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback(); raise
        finally:
            db.close()

    def load(self, db):
        require(db.execute('PRAGMA quick_check').fetchall() == [('ok',)], 'REGISTRY_CORRUPT')
        row = db.execute('SELECT payload,sha FROM registry').fetchall()
        require(len(row) == 1, 'REGISTRY_CORRUPT')
        s = json.loads(row[0][0])
        require(fingerprint(s) == row[0][1] and s['version'] == VERSION
                and s['test'] is self.test, 'REGISTRY_DIVERGENT')
        events = db.execute('SELECT seq,code,sha,previous FROM events ORDER BY seq').fetchall()
        prev = '0'*64
        for i, (seq, code, sha, previous) in enumerate(events, 1):
            require(seq == i and previous == prev and sha == fingerprint([seq, code, previous]), 'AUDIT_DIVERGENT')
            prev = sha
        require(bool(events) and json.loads(events[-1][1])['state_sha'] == fingerprint(s), 'AUDIT_DIVERGENT')
        return s

    def change(self, code, fn):
        with self.db() as db:
            s = self.load(db); now = int(self.clock()*1000)
            require(now >= s['last_ms'], 'CLOCK_ROLLBACK')
            result = fn(s, now); s['last_ms'] = now
            seq, old = db.execute('SELECT seq,sha FROM events ORDER BY seq DESC LIMIT 1').fetchone()
            db.execute('UPDATE registry SET payload=?,sha=?', (canonical(s), fingerprint(s)))
            message = canonical({'code': code, 'state_sha': fingerprint(s)})
            db.execute('INSERT INTO events(code,sha,previous) VALUES(?,?,?)',
                       (message, fingerprint([seq+1, message, old]), old))
            return deepcopy(result)

    def snapshot(self):
        with self.db() as db:
            return deepcopy(self.load(db))

    def approve(self, approval, bound):
        """Seules des décisions épinglées côté serveur sont reconnues en LIVE.

        test=True permet la recette des mêmes transitions, jamais le transport réel.
        Aucun registre OFFLINE_ONLY, approved=True ou reçu client n'est reconnu.
        """
        def apply(s, now):
            require(s['state'] == 'DRAFT', 'APPROVAL_STATE_REFUSED')
            self.proof(approval, 'HUMAN_LIVE_APPROVAL', TRUSTED_APPROVALS)
            self.proof(bound, 'ALL_IN_EUR_BOUND', TRUSTED_BOUNDS)
            for doc in (approval, bound):
                require(doc.get('campaign') == s['campaign'] and doc.get('request_sha256') == s['request_sha256'], 'PROOF_SCOPE_MISMATCH')
                require(integer(doc.get('expires_ms')) and now < doc['expires_ms'], 'PROOF_EXPIRED')
            require(approval.get('max_calls') == 1 and type(approval.get('max_calls')) is int, 'CALL_LIMIT_INVALID')
            require(type(approval.get('human_identity')) is str and bool(approval['human_identity'].strip())
                    and type(approval.get('decision_reference')) is str and bool(approval['decision_reference'].strip()),
                    'HUMAN_DECISION_REFERENCE_REQUIRED')
            require(approval.get('ceiling_eur_micros') == 1_000_000, 'CEILING_INVALID')
            require(integer(bound.get('max_eur_micros'), 1) and bound['max_eur_micros'] <= 1_000_000, 'BUDGET_INSUFFICIENT')
            require(bound.get('all_costs_included') is True, 'BOUND_INCOMPLETE')
            s.update(state='AUTHORIZED', approval=deepcopy(approval), bound=deepcopy(bound))
        return self.change('AUTHORIZED_TEST' if self.test else 'AUTHORIZED_LIVE', apply)

    def proof(self, doc, kind, pins):
        require(type(doc) is dict and doc.get('kind') == kind, 'PROOF_INVALID')
        require(doc.get('test') is self.test, 'PROOF_MODE_MISMATCH')
        if not self.test:
            require(fingerprint(doc) in pins, 'PROOF_NOT_RECOGNIZED')

    def fresh(self, s, request, now):
        require(valid_request(request) and fingerprint(request) == s['request_sha256'], 'REQUEST_CHANGED')
        require(dependencies() == s['dependencies'], 'DEPENDENCY_CHANGED')
        require(0 <= now-s['prepared_ms'] <= 30_000, 'PREPARATION_EXPIRED')
        for doc, kind, pins in [(s['approval'], 'HUMAN_LIVE_APPROVAL', TRUSTED_APPROVALS),
                                (s['bound'], 'ALL_IN_EUR_BOUND', TRUSTED_BOUNDS)]:
            self.proof(doc, kind, pins)
            require(now < doc['expires_ms'], 'PROOF_EXPIRED')

    def reserve(self, request):
        def apply(s, now):
            require(s['state'] == 'AUTHORIZED', 'ALREADY_STARTED_OR_NOT_AUTHORIZED')
            self.fresh(s, request, now)
            s.update(state='RESERVED', reserved_eur_micros=s['bound']['max_eur_micros'])
        return self.change('RESERVED', apply)

    def refresh_draft(self, request):
        """Nouvelle préparation backend du même corps, avant toute autorisation.

        Ne renouvelle ni accord ni borne ; leurs expirations restent inchangées.
        """
        def apply(s,now):
            require(s['state']=='DRAFT' and s['request_sha256']==fingerprint(request)
                    and s['dependencies']==dependencies(),'DRAFT_REFRESH_REFUSED')
            require(valid_request(request),'REQUEST_INVALID')
            s['prepared_ms']=now
        return self.change('DRAFT_REPREPARED',apply)

    def engage(self, request):
        def apply(s, now):
            require(s['state'] == 'RESERVED', 'ALREADY_ENGAGED')
            self.fresh(s, request, now); s['state'] = 'ENGAGED'
        return self.change('ENGAGED', apply)

    def mark_emission(self, request):
        def apply(s, now):
            require(s['state'] == 'ENGAGED' and s['emissions'] == 0, 'SECOND_EMISSION_REFUSED')
            self.fresh(s, request, now); s['emissions'] = 1
        return self.change('EMISSION_COMMITTED', apply)

    def finish(self, code, result_sha=None):
        require(code in {'RECEIVED', 'TIMEOUT', 'INTERRUPTED', 'HTTP_ERROR', 'INVALID_JSON', 'EVIDENCE_FAILED'}, 'OUTCOME_INVALID')
        def apply(s, now):
            require(s['state'] == 'ENGAGED', 'OUTCOME_STATE_REFUSED')
            s.update(state='UNCERTAIN', outcome=code, result_sha256=result_sha)
        return self.change(code, apply)

    def recover(self):
        def apply(s, now):
            if s['state'] in {'RESERVED', 'ENGAGED'}:
                s.update(state='UNCERTAIN', outcome='INTERRUPTED')
        return self.change('RECOVERY_NO_RETRY', apply)

    def revoke(self):
        def apply(s, now):
            s['state'] = 'REVOKED'
        return self.change('REVOKED', apply)

    def reconcile(self, receipt):
        def apply(s, now):
            self.proof(receipt, 'ACTUAL_EUR_COST', TRUSTED_RECEIPTS)
            require(receipt.get('campaign') == s['campaign'] and receipt.get('result_sha256') == s['result_sha256']
                    and s['result_sha256'] is not None, 'RECEIPT_SCOPE_MISMATCH')
            require(integer(receipt.get('amount_eur_micros')), 'COST_UNKNOWN')
            if s['state'] == 'RECONCILED':
                require(s.get('receipt') == receipt, 'RECONCILIATION_CONFLICT'); return
            require(s['state'] == 'UNCERTAIN', 'RECONCILIATION_STATE_REFUSED')
            s.update(actual_eur_micros=receipt['amount_eur_micros'], receipt=deepcopy(receipt))
            s['state'] = 'FROZEN' if receipt['amount_eur_micros'] > s['reserved_eur_micros'] else 'RECONCILED'
        return self.change('RECONCILED', apply)


def dependencies():
    import hashlib
    files = [*sorted((ROOT/'prompts').glob('*.md')),
             *[ROOT/'gary_v5'/n for n in ['generation_contract.py', 'module_rules.py', 'routing.py',
                                        'live_supervisor.py', 'live_transport.py', 'live_evidence.py',
                                        'generation_gateway.py', 'generation_metrics.py', 'visual_export.py','request_policy.py','functional_store.py']]]
    return fingerprint({str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
