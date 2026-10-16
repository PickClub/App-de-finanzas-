"""Synthetic-only APPLY adapter. No clients, connections or commands on import.

Injected clients/verifiers are trust boundaries; no real-data mode or CLI exists.
"""
from dataclasses import dataclass, fields, asdict
from uuid import uuid4
import time

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.decimal128 import Decimal128
from pymongo import ReadPreference, timeout, MongoClient as _DriverClient
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern
from pymongo.errors import PyMongoError

from backend.financial_context import validate_metadata
from backend.history_apply import (
    Authorization, Observation, RunState, Evidence, Conflict, TransientTransaction,
    UnknownCommit, evidence_for, _authorize, _observe,
)
from backend.history_provisioning import Plan, validate_intent
from backend.history_keys import SOURCE_FIELDS, derive_history_keys
from backend.history_apply_lab import LabTarget, LAB_NONCE, check_lab_identity
from backend.history_diagnostics import Target

JOURNAL = 'history_apply_synthetic_journal'
MARKER = 'c3-synthetic-apply-preparation'


@dataclass(frozen=True)
class SyntheticPermit:
    authorization: Authorization
    nonce: str
    journal_uuid: Binary
    absence_independently_attested: bool = False
    approved: bool = False
    mode: str = 'synthetic_only'
    operation: str = 'apply'


def _uuid(value):
    return type(value) is Binary and value.subtype == 4 and len(value) == 16


def _type(value):
    if type(value) is Int64: return 'long'
    if type(value) is int: return 'int'
    if type(value) is float: return 'double'
    if type(value) is str: return 'string'
    if type(value) is bool: return 'bool'
    if value is None: return 'null'
    if type(value) is Decimal128: return 'decimal'
    if type(value) in (bytes, Binary): return 'binData'
    from bson.objectid import ObjectId
    if type(value) is ObjectId: return 'objectId'
    raise Conflict()


def cas_filter(current):
    """Only internally reread sources, using exact BSON types and literal values."""
    predicates = []
    for name in ('_id', *SOURCE_FIELDS):
        field_type = {'$type': '$' + name}
        if name not in current:
            predicates.append({'$eq': [field_type, 'missing']})
        else:
            predicates.extend(({'$eq': [field_type, _type(current[name])]},
                               {'$eq': ['$' + name, {'$literal': current[name]}]}))
    return {'_id': current['_id'], 'user_id': 'default-user',
            '_history_keys': {'$exists': False}, '$expr': {'$and': predicates}}


class SyntheticMongoApplyAdapter:
    """Explicit client injection; constructor validates pure input only.

    Verifier.verify(permit, deadline) must independently attest Observation.
    The preparation marker/registry NEVER substitutes for writer exclusion.
    """
    def __init__(self, client, plan, permit, verifier, *, clock=time.monotonic, own_client=True):
        if (type(permit) is not SyntheticPermit or permit.mode != 'synthetic_only'
                or permit.operation not in ('apply', 'reconcile') or permit.approved is not True
                or permit.absence_independently_attested is not True
                or type(permit.nonce) is not str
                or any(c not in '0123456789abcdef' for c in permit.nonce)
                or not _uuid(permit.journal_uuid) or verifier is None):
            raise Conflict()
        if type(permit.authorization) is not Authorization or type(plan) is not Plan:
            raise Conflict()
        self.auth = permit.authorization
        self.target = self.auth.target
        self.lab = type(self.target) is LabTarget
        if self.lab:
            if permit.nonce != LAB_NONCE or permit.journal_uuid != self.target.journal_uuid:
                raise Conflict()
        elif (type(self.target) is not Target or len(permit.nonce) != 32
              or isinstance(client, _DriverClient)
              or not type(client).__module__.startswith('backend.tests.')):
            # Preserve the old offline fixtures, never a development client path.
            raise Conflict()
        if self.target.database != 'test_c3_apply_' + permit.nonce:
            raise Conflict()
        _authorize(plan, self.target, self.auth, clock())
        self.client, self.plan, self.permit, self.verifier = client, plan, permit, verifier
        self.clock, self.own_client = clock, own_client
        self.deadline = clock() + 30
        self.owner = uuid4().hex
        self.controller = None
        self.claimed = False
        self.closed = False
        self.active = []
        self.metrics = {'calls': 0, 'bson_bytes': 0, 'documents_read': 0,
                        'sessions_opened': 0, 'sessions_closed': 0}
        self.allowed = {evidence_for(plan, i, self.auth).key: i for i in plan.intents}
        self.db = client[self.target.database]  # Driver handles are lazy; no command here.
        self.movements = self.db['transactions']
        self.metadata = self.db['moneyflow_metadata'].with_options(
            read_concern=ReadConcern('majority'), read_preference=ReadPreference.PRIMARY)
        self.journal = self.db[JOURNAL].with_options(
            read_concern=ReadConcern('majority'), write_concern=WriteConcern('majority'),
            read_preference=ReadPreference.PRIMARY)

    def _remaining(self, deadline=None):
        deadline = min(self.deadline, deadline if deadline is not None else self.deadline)
        remaining = deadline - self.clock()
        if self.closed or remaining <= 0:
            raise Conflict()
        _authorize(self.plan, self.target, self.auth, self.clock())
        return remaining

    def _call(self, operation, *, deadline=None):
        self.metrics['calls'] += 1
        if self.metrics['calls'] > 10000: raise Conflict()
        with timeout(self._remaining(deadline)):
            return operation()

    def _bytes(self, value):
        size = len(BSON.encode(value))
        self.metrics['bson_bytes'] += size
        if size > 1048576 or self.metrics['bson_bytes'] > 33554432: raise Conflict()
        return value

    def _record(self):
        record = {'_id': 'execution', 'contract': 1, 'mode': 'synthetic_only',
                'nonce': self.permit.nonce, 'destination': self.target.binding(),
                'collection_uuid': self.target.collection_uuid, 'journal_uuid': self.permit.journal_uuid,
                'environment_id': self.target.environment_id, 'user_id': self.target.user_id,
                'run_id': self.plan.run_id, 'plan_digest': self.plan.digest,
                'revision': self.auth.revision, 'epoch': self.auth.exclusion_epoch,
                'version': self.target.version, 'generation': self.target.generation,
                'scope': self.plan.scope, 'owner': self.owner}
        if self.lab:
            record['metadata_uuid'] = self.target.metadata_uuid
        return record

    def observe(self, session=None, deadline=None):
        remaining = self._remaining(deadline)
        end = self.clock() + remaining
        observed = self.verifier.verify(self.permit, end)
        _observe(observed, self.target, self.auth)
        if self.lab:
            try:
                check_lab_identity(self.client, self.target, lambda command:
                    self._call(lambda: self.client.admin.command(command), deadline=end))
            except Exception:
                raise Conflict() from None
        else:
            if self.client.address != ('127.0.0.1', 27018): raise Conflict()
            hello = self._call(lambda: self.client.admin.command('hello'), deadline=end)
            if (not hello.get('isWritablePrimary') or hello.get('setName') != 'app_finanzas_dev_rs'
                    or not hello.get('logicalSessionTimeoutMinutes')): raise Conflict()
            build = self._call(lambda: self.client.admin.command('buildInfo'), deadline=end)
            if not str(build.get('version', '')).startswith('8.0.'): raise Conflict()
        pins = [('transactions', self.target.collection_uuid), (JOURNAL, self.permit.journal_uuid)]
        if self.lab:
            pins.append(('moneyflow_metadata', self.target.metadata_uuid))
        for name, expected in pins:
            def info(name=name):
                with self.db.list_collections(filter={'name': name}) as cursor:
                    return list(cursor)
            rows = self._call(info, deadline=end)
            if len(rows) != 1 or rows[0].get('info', {}).get('uuid') != expected: raise Conflict()
        metadata = self._call(lambda: self.metadata.find_one(
            {'_id': 'financial-context'}, session=session), deadline=end)
        if type(metadata) is not dict: raise Conflict()
        self._bytes(metadata)
        try: validate_metadata(metadata, self.target.environment_id)
        except Exception: raise Conflict() from None
        marker = self._call(lambda: self.metadata.find_one({'_id': MARKER}, session=session), deadline=end)
        expected_marker = {'_id': MARKER, 'mode': 'synthetic_only', 'nonce': self.permit.nonce,
                           'collection_uuid': self.target.collection_uuid, 'journal_uuid': self.permit.journal_uuid,
                           'environment_id': self.target.environment_id}
        if self.lab:
            expected_marker['metadata_uuid'] = self.target.metadata_uuid
        if type(marker) is not dict: raise Conflict()
        self._bytes(marker)
        if marker != expected_marker: raise Conflict()
        return observed

    def bind_controller(self, controller, binding):
        expected = (self.plan.run_id, self.plan.digest, self.target.binding(),
                    self.auth.revision, self.auth.exclusion_epoch)
        if type(controller) is not RunState or binding != expected: raise Conflict()
        if self.controller is not None and self.controller is not controller: raise Conflict()
        self.observe()
        if not self.claimed:
            if self.permit.operation == 'apply':
                # No upsert or lease: existing record permanently blocks another owner.
                try:
                    result = self._call(lambda: self.journal.insert_one(self._bytes(self._record())))
                    if result.acknowledged is not True: raise Conflict()
                except PyMongoError: raise Conflict() from None
            else:
                record = self._call(lambda: self.journal.find_one({'_id': 'execution'}))
                if type(record) is dict: self._bytes(record)
                expected_record = self._record()
                if type(record) is not dict or not isinstance(record.get('owner'), str): raise Conflict()
                expected_record['owner'] = record['owner']
                if record != expected_record: raise Conflict()
            self.claimed = True
        self.controller = controller

    def begin(self, deadline):
        if self.permit.operation != 'apply' or not self.claimed or self.controller is None:
            raise Conflict()
        if self.controller.pending is not None or self.controller.halted: raise Conflict()
        self.observe(deadline=deadline)
        session = self._call(lambda: self.client.start_session(causal_consistency=False), deadline=deadline)
        self.metrics['sessions_opened'] += 1
        try:
            session.start_transaction(read_concern=ReadConcern('snapshot'), write_concern=WriteConcern('majority'),
                                      read_preference=ReadPreference.PRIMARY,
                                      max_commit_time_ms=max(1, min(5000, int(self._remaining(deadline)*1000))))
        except Exception:
            with timeout(2): session.end_session()
            self.metrics['sessions_closed'] += 1
            raise Conflict() from None
        tx = SyntheticTransaction(self, session, deadline)
        self.active.append(tx)
        return tx

    def receipt(self, key, session=None, deadline=None):
        if not self.claimed or self.controller is None or key not in self.allowed: raise Conflict()
        if session is None:
            self.observe(deadline=deadline)
        elif not any(tx.session is session and not tx.closed for tx in self.active):
            raise Conflict()
        record = self._call(lambda: self.journal.find_one({'_id': 'receipt:' + key}, session=session), deadline=deadline)
        if record is None: return None
        self._bytes(record)
        names = {f.name for f in fields(Evidence)}
        if set(record) != names | {'_id'} or record['_id'] != 'receipt:' + key: raise Conflict()
        evidence = Evidence(**{name: record[name] for name in names})
        if evidence != evidence_for(self.plan, self.allowed[key], self.auth): raise Conflict()
        return evidence

    def close(self, deadline):
        if self.closed: return
        failed = False
        end = min(deadline, self.clock()+2)
        for tx in list(self.active):
            try: tx.close(end)
            except Exception: failed = True
        if self.own_client:
            try:
                with timeout(max(.001, end-self.clock())): self.client.close()
            except Exception: failed = True
        self.closed = True
        if failed: raise Conflict()


class SyntheticTransaction:
    def __init__(self, adapter, session, deadline):
        self.adapter, self.session, self.deadline = adapter, session, deadline
        self.current = None
        self.intent = None
        self.staged = False
        self.sent = False
        self.uncertain = False
        self.confirmed = False
        self.closed = False

    def _valid(self):
        if (self.closed or self not in self.adapter.active or not self.adapter.claimed
                or self.adapter.permit.operation != 'apply' or self.adapter.controller is None):
            raise Conflict()

    def observe(self):
        self._valid()
        return self.adapter.observe(self.session, self.deadline)

    def receipt(self, key):
        self._valid()
        return self.adapter.receipt(key, self.session, self.deadline)

    def _operation(self, callback):
        try: return self.adapter._call(callback, deadline=self.deadline)
        except PyMongoError as error:
            if error.has_error_label('UnknownTransactionCommitResult'):
                raise UnknownCommit() from None
            if error.has_error_label('TransientTransactionError'):
                raise TransientTransaction() from None
            raise Conflict() from None

    def read(self, physical_id):
        self._valid()
        if self.current is not None: raise Conflict()
        matches = [i for i in self.adapter.plan.intents if i.physical_id == physical_id]
        if len(matches) != 1: raise Conflict()
        self.intent = matches[0]
        try: value = BSON(physical_id).decode()['value']
        except Exception: raise Conflict() from None
        document = self._operation(lambda: self.adapter.movements.find_one(
            {'_id': value, 'user_id': self.adapter.target.user_id}, session=self.session))
        if type(document) is not dict: raise Conflict()
        self.adapter.metrics['documents_read'] += 1
        if self.adapter.metrics['documents_read'] > 10000: raise Conflict()
        self.adapter._bytes(document)
        if validate_intent(self.adapter.plan, self.intent, document, self.adapter.target) != 'preconditions_match':
            raise Conflict()
        self.current = bytes(BSON.encode(document))
        return document

    def stage(self, current_bson, proposed_bson, evidence):
        self._valid()
        if self.staged or self.current is None or current_bson != self.current: raise Conflict()
        current = BSON(self.current).decode()
        expected = evidence_for(self.adapter.plan, self.intent, self.adapter.auth)
        if type(evidence) is not Evidence or evidence != expected: raise Conflict()
        if validate_intent(self.adapter.plan, self.intent, current, self.adapter.target) != 'preconditions_match': raise Conflict()
        proposed = derive_history_keys(current, self.adapter.target.generation)
        if proposed['state'] != 'ready' or BSON.encode({'value': proposed}) != proposed_bson: raise Conflict()
        self.observe()
        self.adapter._bytes({**current, '_history_keys': proposed})
        record = {'_id': 'receipt:' + evidence.key, **asdict(evidence)}
        self.adapter._bytes(record)
        if len(BSON.encode({**current, '_history_keys': proposed})) + len(BSON.encode(record)) > 1048576: raise Conflict()
        result = self._operation(lambda: self.adapter.movements.update_one(
            cas_filter(current), {'$set': {'_history_keys': proposed}}, upsert=False, session=self.session))
        if result.acknowledged is not True or result.matched_count != 1 or result.modified_count != 1: raise Conflict()
        result = self._operation(lambda: self.adapter.journal.insert_one(record, session=self.session))
        if result.acknowledged is not True: raise Conflict()
        self.staged = True

    def commit(self):
        self._valid()
        if not self.staged or self.closed: raise Conflict()
        if self.confirmed: return
        try:
            # On an uncertain commit, never start another transaction or call stage again.
            if not self.sent: self.observe()
            else: self.adapter.observe(deadline=self.deadline)
            self.sent = True
            self.adapter._call(lambda: self.session.commit_transaction(), deadline=self.deadline)
            self.confirmed = True
            self.uncertain = False
        except Exception as error:
            if (self.uncertain or isinstance(error, PyMongoError) and error.has_error_label('UnknownTransactionCommitResult')):
                self.uncertain = True
                raise UnknownCommit() from None
            if isinstance(error, PyMongoError) and error.has_error_label('TransientTransactionError'):
                self.sent = False
                raise TransientTransaction() from None
            if self.sent:
                self.uncertain = True
                raise UnknownCommit() from None
            raise Conflict() from None

    def close(self, deadline):
        if self.closed: return
        failed = False
        try:
            with timeout(max(.001, min(deadline, self.adapter.clock()+2)-self.adapter.clock())):
                # No explicit abort after an uncertain commit. Cleanup cannot prove rollback.
                if not self.sent and self.session.in_transaction: self.session.abort_transaction()
                if self.uncertain and self.session.in_transaction:
                    # Do not invoke an end_session implementation that would abort this transaction.
                    failed = True
                else:
                    self.session.end_session()
                    self.adapter.metrics['sessions_closed'] += 1
        except Exception: failed = True
        self.closed = True
        if self in self.adapter.active: self.adapter.active.remove(self)
        if failed: raise Conflict()
