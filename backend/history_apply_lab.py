"""Closed laboratory profile. No client construction or I/O on import."""
from dataclasses import dataclass, field
import hashlib
from pathlib import Path
import os
import stat

from bson import BSON
from bson.binary import Binary
from backend.financial_context import validate_environment_id, validate_metadata
from backend.history_keys import VERSION
from backend.history_diagnostics import StopDiagnostic
from backend.history_diagnostics_mongodb import MongoSnapshotReader

LAB_URI = 'mongodb://127.0.0.1:27019/?replicaSet=moneyflow_c3_apply_test_rs&directConnection=true'
LAB_ADDRESS = ('127.0.0.1', 27019)
LAB_REPLICA = 'moneyflow_c3_apply_test_rs'
LAB_DATABASE = 'test_c3_apply_7e62d1a31cc9'
LAB_NONCE = '7e62d1a31cc9'
LAB_USER = 'c3_apply'
LAB_MECHANISM = 'SCRAM-SHA-256'


def physical_uuid(value):
    return type(value) is Binary and value.subtype == 4 and len(value) == 16


@dataclass(frozen=True)
class LabTarget:
    collection_uuid: Binary
    journal_uuid: Binary
    metadata_uuid: Binary
    environment_id: str
    generation: int
    approved: bool = False
    physical_pins_approved: bool = False
    uri: str = LAB_URI
    database: str = LAB_DATABASE
    collection: str = 'transactions'
    user_id: str = 'default-user'
    version: int = VERSION
    nonce: str = LAB_NONCE
    replica: str = LAB_REPLICA
    auth_user: str = LAB_USER
    mechanism: str = LAB_MECHANISM

    def validate(self):
        if (self.uri != LAB_URI or self.database != LAB_DATABASE
                or self.collection != 'transactions' or self.user_id != 'default-user'
                or self.nonce != LAB_NONCE or self.replica != LAB_REPLICA
                or self.auth_user != LAB_USER or self.mechanism != LAB_MECHANISM
                or self.approved is not True or self.physical_pins_approved is not True
                or type(self.version) is not int or self.version != VERSION
                or type(self.generation) is not int or not 1 <= self.generation <= 2147483647
                or not all(physical_uuid(x) for x in
                           (self.collection_uuid, self.journal_uuid, self.metadata_uuid))
                or len({self.collection_uuid, self.journal_uuid, self.metadata_uuid}) != 3):
            raise StopDiagnostic('invalid_lab_target')
        try:
            validate_environment_id(self.environment_id)
        except Exception:
            raise StopDiagnostic('invalid_lab_target') from None

    def binding(self):
        self.validate()
        return hashlib.sha256(BSON.encode({
            'deployment': 'closed_c3_apply_lab_v1', 'address': list(LAB_ADDRESS),
            'replica': self.replica, 'database': self.database, 'collection': self.collection,
            'uuid': self.collection_uuid, 'journal_uuid': self.journal_uuid,
            'metadata_uuid': self.metadata_uuid, 'environment_id': self.environment_id,
            'nonce': self.nonce, 'auth_user': self.auth_user, 'mechanism': self.mechanism,
            'user_id': self.user_id, 'version': self.version, 'generation': self.generation,
        })).hexdigest()


@dataclass(frozen=True)
class LabCredentials:
    password: str = field(repr=False)
    username: str = LAB_USER
    mechanism: str = LAB_MECHANISM

    def validate(self):
        if (self.username != LAB_USER or self.mechanism != LAB_MECHANISM
                or type(self.password) is not str or not self.password):
            raise StopDiagnostic('invalid_lab_credentials')


def load_lab_credentials():
    """Explicit private file read only; never connect, log or accept CLI secrets."""
    directory = Path(os.environ.get('XDG_DATA_HOME', str(Path.home() / '.local/share')))
    directory = directory / 'moneyflow-c3-labs' / LAB_NONCE
    path = directory / 'apply'
    try:
        if (directory.is_symlink() or path.is_symlink()
                or path.resolve().is_relative_to(Path(__file__).resolve().parent.parent)
                or stat.S_IMODE(directory.stat().st_mode) != 0o700):
            raise ValueError()
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        with os.fdopen(fd, 'r') as stream:
            info = os.fstat(stream.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or stat.S_IMODE(info.st_mode) != 0o600 or info.st_size > 4096):
                raise ValueError()
            credentials = LabCredentials(stream.read(4097).strip())
        credentials.validate()
        return credentials
    except Exception:
        raise StopDiagnostic('private_credentials_unavailable') from None


def lab_client_options(target, credentials):
    """Pure options, not a factory. Runner's execution gate remains closed."""
    if type(target) is not LabTarget or type(credentials) is not LabCredentials:
        raise StopDiagnostic('invalid_lab_profile')
    target.validate()
    credentials.validate()
    return {'host': LAB_URI, 'username': LAB_USER, 'password': credentials.password,
            'authSource': 'admin', 'authMechanism': LAB_MECHANISM, 'connect': False,
            'serverSelectionTimeoutMS': 3000, 'connectTimeoutMS': 3000,
            'socketTimeoutMS': 5000, 'maxPoolSize': 1,
            'retryReads': False, 'retryWrites': False}


def check_lab_identity(client, target, command):
    """Only fixed read commands; the caller supplies its bounded command wrapper."""
    if type(target) is not LabTarget:
        raise StopDiagnostic('invalid_lab_profile')
    target.validate()
    if client.address != LAB_ADDRESS:
        raise StopDiagnostic('destination_mismatch')
    hello = command('hello')
    if (hello.get('setName') != LAB_REPLICA or not hello.get('isWritablePrimary')
            or not hello.get('logicalSessionTimeoutMinutes')):
        raise StopDiagnostic('destination_mismatch')
    if command('buildInfo').get('version') != '8.0.32':
        raise StopDiagnostic('destination_mismatch')
    auth = command({'connectionStatus': 1, 'showPrivileges': False}).get('authInfo', {})
    if (auth.get('authenticatedUsers') != [{'user': LAB_USER, 'db': 'admin'}]
            or auth.get('authenticatedUserRoles') != [{'role': 'c3_apply_limited', 'db': 'admin'}]):
        raise StopDiagnostic('invalid_lab_credentials')


class LabSnapshotReader(MongoSnapshotReader):
    """Reuse snapshot traversal; replace only the development identity guard."""
    def __init__(self, client, target, *args, **kwargs):
        if type(target) is not LabTarget:
            raise StopDiagnostic('invalid_lab_profile')
        super().__init__(client, target, *args, **kwargs)

    def _identity_current(self, deadline):
        from pymongo import timeout
        import time
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StopDiagnostic('deadline_exceeded')
        with timeout(remaining):
            check_lab_identity(self.client, self.target, self.client.admin.command)
            for name, expected in (('transactions', self.target.collection_uuid),
                                   ('history_apply_synthetic_journal', self.target.journal_uuid),
                                   ('moneyflow_metadata', self.target.metadata_uuid)):
                with self.db.list_collections(filter={'name': name}) as cursor:
                    rows = list(cursor)
                if len(rows) != 1 or rows[0].get('info', {}).get('uuid') != expected:
                    raise StopDiagnostic('destination_mismatch')
            validate_metadata(self.db.moneyflow_metadata.find_one(
                {'_id': 'financial-context'}), self.target.environment_id)


@dataclass(frozen=True)
class LabObserverTarget:
    """Candidate pins for reading only; never a LabTarget authorization."""
    collection_uuid: Binary
    journal_uuid: Binary
    metadata_uuid: Binary
    environment_id: str
    generation: int
    uri: str = LAB_URI
    database: str = LAB_DATABASE
    collection: str = 'transactions'
    user_id: str = 'default-user'
    version: int = VERSION
    nonce: str = LAB_NONCE
    replica: str = LAB_REPLICA
    auth_user: str = 'c3_observer'
    auth_role: str = 'c3_observer_limited'
    mechanism: str = LAB_MECHANISM

    def validate(self):
        if (self.uri != LAB_URI or self.database != LAB_DATABASE
                or self.collection != 'transactions' or self.user_id != 'default-user'
                or self.nonce != LAB_NONCE or self.replica != LAB_REPLICA
                or self.auth_user != 'c3_observer' or self.auth_role != 'c3_observer_limited'
                or self.mechanism != LAB_MECHANISM
                or type(self.version) is not int or self.version != VERSION
                or type(self.generation) is not int or not 1 <= self.generation <= 2147483647
                or not all(physical_uuid(x) for x in
                           (self.collection_uuid, self.journal_uuid, self.metadata_uuid))
                or len({self.collection_uuid, self.journal_uuid, self.metadata_uuid}) != 3):
            raise StopDiagnostic('invalid_observer_target')
        try:
            validate_environment_id(self.environment_id)
        except Exception:
            raise StopDiagnostic('invalid_observer_target') from None

    def binding(self):
        self.validate()
        from dataclasses import asdict
        return hashlib.sha256(BSON.encode({
            'contract': 'closed_observer_plan_v1', 'candidate_pins_only': True,
            **asdict(self),
        })).hexdigest()


class LabObserverSnapshotReader(MongoSnapshotReader):
    """Read-only traversal: one real session, one T, no transaction or writes."""
    def __init__(self, client, target, *, own_client=False, audit=None):
        if type(target) is not LabObserverTarget:
            raise StopDiagnostic('invalid_observer_target')
        super().__init__(client, target, own_client=own_client, audit=audit)
        self.session = None
        self.deadline = None

    def _shared_session(self):
        if self.closed:
            raise StopDiagnostic('reader_closed')
        if self.session is None:
            self.session = self.client.start_session(causal_consistency=False)
            self.metrics['sessions_opened'] += 1
        return self.session

    def _remaining_read(self, deadline):
        import time
        if self.deadline is not None:
            deadline = min(deadline, self.deadline)
        remaining = deadline - time.monotonic()
        if self.closed or remaining <= 0:
            raise StopDiagnostic('deadline_exceeded')
        return remaining

    def _validate(self, req):
        super()._validate(req)
        return self._remaining_read(req.deadline)

    def _identity_current(self, deadline):
        from pymongo import timeout
        with timeout(self._remaining_read(deadline)):
            self.target.validate()
            if self.client.address != LAB_ADDRESS:
                raise StopDiagnostic('destination_mismatch')
            session = self._shared_session()
            hello = self.client.admin.command('hello', session=session)
            if (not hello.get('isWritablePrimary') or hello.get('setName') != LAB_REPLICA
                    or not hello.get('logicalSessionTimeoutMinutes')):
                raise StopDiagnostic('destination_mismatch')
            if self.client.admin.command('buildInfo', session=session).get('version') != '8.0.32':
                raise StopDiagnostic('destination_mismatch')
            auth = self.client.admin.command({'connectionStatus': 1, 'showPrivileges': False},
                                             session=session).get('authInfo', {})
            if (auth.get('authenticatedUsers') != [{'user': 'c3_observer', 'db': 'admin'}]
                    or auth.get('authenticatedUserRoles') != [{'role': 'c3_observer_limited', 'db': 'admin'}]):
                raise StopDiagnostic('invalid_observer_credentials')
            for name, expected in (('transactions', self.target.collection_uuid),
                                   ('history_apply_synthetic_journal', self.target.journal_uuid),
                                   ('moneyflow_metadata', self.target.metadata_uuid)):
                with self.db.list_collections(filter={'name': name}, session=session) as cursor:
                    rows = list(cursor)
                if len(rows) != 1 or rows[0].get('info', {}).get('uuid') != expected:
                    raise StopDiagnostic('destination_mismatch')

    def acquire_snapshot(self, deadline):
        import time
        if self.T is not None or not 0 < deadline - time.monotonic() <= 30:
            raise StopDiagnostic('invalid_snapshot_acquisition')
        self.deadline = deadline
        return super().acquire_snapshot(deadline)

    def _metadata_snapshot(self, deadline, *, select=False):
        from pymongo import timeout
        from bson.timestamp import Timestamp
        remaining = self._remaining_read(deadline)
        concern = {'level': 'snapshot'}
        if not select:
            concern['atClusterTime'] = self.T
        command = {'find': 'moneyflow_metadata', 'filter': {'_id': 'financial-context'},
                   'limit': 1, 'singleBatch': True, 'readConcern': concern,
                   'maxTimeMS': max(1, min(10000, int(remaining * 1000)))}
        with timeout(remaining):
            reply = self._initial_command(command, self._shared_session())
        cursor = reply.get('cursor', {})
        if cursor.get('id') or cursor.get('ns') != self.target.database + '.moneyflow_metadata':
            raise StopDiagnostic('invalid_response')
        docs = cursor.get('firstBatch', [])
        if len(docs) != 1:
            raise StopDiagnostic('destination_mismatch')
        try:
            validate_metadata(docs[0], self.target.environment_id)
        except Exception:
            raise StopDiagnostic('destination_mismatch') from None
        if select:
            selected = reply.get('atClusterTime') or cursor.get('atClusterTime')
            if type(selected) is not Timestamp:
                raise StopDiagnostic('invalid_T')
            self.T = selected
            if self.audit:
                self.audit.T = selected
        self._attest(reply)

    def _stream(self, req, command):
        from pymongo import timeout
        from pymongo.command_cursor import CommandCursor
        self._guard(req)
        session = self._shared_session()
        handle = {'session': session, 'cursor': 0, 'collection': self.collection,
                  'T': self.T, 'binding': req.binding}
        self.active.append(handle)
        try:
            remaining = self._validate(req)
            initial = {**command, 'readConcern': {'level': 'snapshot', 'atClusterTime': self.T},
                       'maxTimeMS': max(1, min(10000, int(remaining * 1000)))}
            self.anchors.add((self.T.time, self.T.inc))
            self.metrics['initial_snapshot_commands'] += 1
            with timeout(remaining):
                reply = self._initial_command(initial, session)
            cursor = reply['cursor']
            if cursor['ns'] != self.target.database + '.' + self.collection:
                self.metrics['cleanup_errors'] += 1
                raise StopDiagnostic('destination_mismatch')
            handle['cursor'] = cursor['id']
            self._attest(reply)
            command_cursor = CommandCursor(self.db[self.collection], cursor, self.client.address,
                batch_size=min(req.batch_documents, 32), session=session, explicit_session=True)
            handle['command_cursor'] = command_cursor
            while True:
                try:
                    with timeout(self._validate(req)):
                        row = next(command_cursor)
                except StopIteration:
                    if self.audit:
                        self.audit.check()
                    break
                if self.audit:
                    self.audit.check()
                yield bytes(BSON.encode(row))
        finally:
            self._release(handle)

    def _release(self, handle, deadline=None):
        from pymongo import timeout
        import time
        if handle not in self.active:
            return
        end = deadline or time.monotonic() + 2
        try:
            with timeout(max(.001, end - time.monotonic())):
                cursor = handle.get('command_cursor')
                if cursor is not None:
                    if cursor.cursor_id:
                        self.metrics['cursor_kills'] += 1
                    cursor.close()
                elif handle['cursor']:
                    self.db.command({'killCursors': self.collection, 'cursors': [handle['cursor']]},
                                    session=self.session)
                    self.metrics['cursor_kills'] += 1
        except Exception:
            self.metrics['cleanup_errors'] += 1
        finally:
            self.active.remove(handle)

    def close(self):
        from pymongo import timeout
        import time
        if self.closed:
            return
        end = time.monotonic() + 2
        for handle in list(self.active):
            self._release(handle, end)
        if self.session is not None:
            try:
                with timeout(max(.001, end - time.monotonic())):
                    self.session.end_session()
                self.metrics['sessions_closed'] += 1
            except Exception:
                self.metrics['cleanup_errors'] += 1
        if self.own_client:
            try:
                with timeout(max(.001, end - time.monotonic())):
                    self.client.close()
            except Exception:
                self.metrics['cleanup_errors'] += 1
        self.closed = True


@dataclass(frozen=True)
class ObserverPlanEvidence:
    plan: object = field(repr=False)
    metrics: dict = field(repr=False)

    def public_report(self):
        return {**self.plan.public_report(), 'read_only': True, 'pins_approved': False,
                'apply_authorized': False, 'metrics': dict(self.metrics),
                'writer_exclusion_asserted': False}


def build_observer_plan(client, target, run_id, *, limits=None, audit=None):
    """In-memory evidence only. Never creates a client or a write authorization."""
    import time
    from backend.history_diagnostics import Limits
    from backend.history_provisioning import build_plan
    limits = Limits() if limits is None else limits
    if (type(limits) is not Limits or type(limits.seconds) not in (int, float)
            or not 0 < limits.seconds <= 30
            or any(type(getattr(limits, name)) is not int
                   or not 0 < getattr(limits, name) <= maximum for name, maximum in
                   (('batch_documents', 100), ('batch_bytes', 1048576),
                    ('history_documents', 10000), ('total_bytes', 33554432), ('requests', 10000)))):
        raise StopDiagnostic('invalid_limits')
    reader = LabObserverSnapshotReader(client, target, own_client=True, audit=audit)
    try:
        with reader:
            T = reader.acquire_snapshot(time.monotonic() + limits.seconds)
            plan = build_plan(reader, target, run_id, T, limits=limits)
    except StopDiagnostic:
        raise
    except Exception:
        raise StopDiagnostic('observer_read_failed') from None
    if reader.metrics['cleanup_errors']:
        raise StopDiagnostic('cleanup_failed')
    return ObserverPlanEvidence(plan, dict(reader.metrics))
