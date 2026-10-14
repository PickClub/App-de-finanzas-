"""Offline APPLY orchestration. Only injected fake adapters; no client or storage.

The adapter contract is a simulation requirement, not a MongoDB guarantee.
"""
from dataclasses import dataclass, field, asdict
import hashlib
import time
import math
from typing import Protocol

from bson import BSON

from backend.history_diagnostics import Target
from backend.history_keys import derive_history_keys
from backend.history_provisioning import Plan, Intent, validate_intent, reversal_status


class Conflict(Exception):
    pass


class TransientTransaction(Exception):
    """Fixture proves the transaction aborted; retry the whole transaction."""


class UnknownCommit(Exception):
    """Fixture cannot determine commit result; retry only this commit."""


@dataclass(frozen=True)
class Authorization:
    run_id: str
    plan_digest: str
    target: Target
    scope: str
    revision: str
    exclusion_epoch: str
    expires_at: float
    approved: bool = False


@dataclass(frozen=True)
class Observation:
    target: Target
    exclusion_epoch: str
    writers_excluded: bool = False
    ddl_excluded: bool = False
    metadata_stable: bool = False
    uniqueness_complete: bool = False
    duplicate_groups: int = 0


@dataclass(frozen=True)
class Budgets:
    documents: int = 10000
    document_bytes: int = 1048576
    total_bytes: int = 33554432
    seconds: float = 30
    transaction_seconds: float = 5
    transaction_attempts: int = 3
    commit_attempts: int = 3


@dataclass(frozen=True)
class Evidence:
    key: str
    run_id: str
    destination: str
    plan_digest: str
    intent_digest: str
    physical_id: bytes = field(repr=False)
    source_sha256: str = field(repr=False)
    proposed_keys: bytes = field(repr=False)
    revision: str
    exclusion_epoch: str
    state: str = 'confirmed'


@dataclass
class RunState:
    """Private in-memory controller state. MUST survive reuse of the fake adapter.

    It is not a durable bitácora or proof of exclusion across process restarts.
    """
    binding: tuple | None = field(default=None, repr=False)
    pending: Intent | None = field(default=None, repr=False)
    halted: bool = False


class Adapter(Protocol):
    def bind_controller(self, controller, binding): ...
    def observe(self) -> Observation: ...
    def begin(self, deadline): ...
    def receipt(self, key) -> Evidence | None: ...
    def close(self, deadline): ...


def evidence_for(plan, intent, auth):
    identity = {'contract': 1, 'destination': plan.destination_id,
                'run': plan.run_id, 'physical_id': intent.physical_id}
    key = hashlib.sha256(BSON.encode(identity)).hexdigest()
    return Evidence(key, plan.run_id, plan.destination_id, plan.digest, intent.digest(),
                    intent.physical_id, intent.source_sha256, intent.proposed_keys,
                    auth.revision, auth.exclusion_epoch)


def _authorize(plan, target, auth, now):
    if type(plan) is not Plan or not plan.eligible_for_review or type(auth) is not Authorization:
        raise Conflict()
    target.validate()
    if (auth.approved is not True or auth.target != target or plan.destination_id != target.binding()
            or auth.run_id != plan.run_id or auth.plan_digest != plan.digest or auth.scope != plan.scope
            or type(auth.revision) is not str or len(auth.revision) != 40
            or any(c not in '0123456789abcdef' for c in auth.revision)
            or type(auth.exclusion_epoch) is not str or not auth.exclusion_epoch
            or type(auth.expires_at) not in (int, float) or not math.isfinite(auth.expires_at)
            or not now < auth.expires_at):
        raise Conflict()


def _observe(observation, target, auth):
    if (type(observation) is not Observation or observation.target != target
            or observation.exclusion_epoch != auth.exclusion_epoch
            or observation.writers_excluded is not True or observation.ddl_excluded is not True
            or observation.metadata_stable is not True or observation.uniqueness_complete is not True
            or type(observation.duplicate_groups) is not int or observation.duplicate_groups != 0):
        raise Conflict()


def _budgets(value):
    maximum = Budgets()
    if type(value) is not Budgets:
        raise Conflict()
    for name in ('documents', 'document_bytes', 'total_bytes', 'transaction_attempts', 'commit_attempts'):
        n = getattr(value, name)
        if type(n) is not int or not 0 < n <= getattr(maximum, name):
            raise Conflict()
    for name in ('seconds', 'transaction_seconds'):
        n = getattr(value, name)
        if type(n) not in (int, float) or not 0 < n <= getattr(maximum, name):
            raise Conflict()


def _report(state, confirmed, recovered, error, attempts, commits, used):
    return {'state': state, 'confirmed_documents': confirmed, 'recovered_documents': recovered,
            'error': error, 'metrics': {'transaction_attempts': attempts, 'commit_attempts': commits,
                                      'processed_bytes': used},
            'offline_simulation': True, 'coverage_complete_asserted': False,
            'financial_correctness_asserted': False, 'certificate_issued': False,
            'indexed_reads_allowed': False, 'operational_apply_authorized': False}


def apply_plan(adapter: Adapter, plan, target, auth, controller: RunState, *,
               budgets=Budgets(), clock=time.monotonic):
    """Transaction fake must stage only $set of keys + evidence, then commit both.

    stage(current BSON, proposed BSON, Evidence) must CAS the reread document;
    commit() retries reuse that SAME transaction. No upsert or global rollback.
    """
    started = clock()
    confirmed = recovered = attempts = commits = used = 0
    state, error = 'blocked', None
    tx = None
    invalid_controller = type(controller) is not RunState
    if invalid_controller:
        controller = RunState()  # Only safe cleanup/reporting; never authorize this substitute.
    try:
        _budgets(budgets)
        _authorize(plan, target, auth, clock())
        if invalid_controller:
            raise Conflict()
        binding = (plan.run_id, plan.digest, target.binding(), auth.revision, auth.exclusion_epoch)
        if controller.binding not in (None, binding):
            raise Conflict()
        adapter.bind_controller(controller, binding)
        controller.binding = binding
        if controller.pending is not None:
            return _report('uncertain', 0, 0, 'reconciliation_required', 0, 0, 0)
        if (controller.halted or len(plan.intents) > budgets.documents
                or len({i.physical_id for i in plan.intents}) != len(plan.intents)):
            raise Conflict()
        deadline = started + budgets.seconds
        def guard(reader):
            if clock() >= deadline:
                raise Conflict()
            _authorize(plan, target, auth, clock())
            _observe(reader.observe(), target, auth)
        guard(adapter)
        for intent in plan.intents:
            evidence = evidence_for(plan, intent, auth)
            finished = False
            for _ in range(budgets.transaction_attempts):
                guard(adapter)
                attempts += 1
                tx_deadline = min(deadline, clock() + budgets.transaction_seconds)
                tx = adapter.begin(tx_deadline)
                try:
                    guard(tx)
                    existing = tx.receipt(evidence.key)
                    if existing is not None:
                        if type(existing) is not Evidence or existing != evidence:
                            raise Conflict()
                        recovered += 1
                        finished = True
                        break
                    current = tx.read(intent.physical_id)
                    if validate_intent(plan, intent, current, target) != 'preconditions_match':
                        raise Conflict()
                    proposed = derive_history_keys(current, target.generation)
                    if proposed['state'] != 'ready' or BSON.encode({'value': proposed}) != intent.proposed_keys:
                        raise Conflict()
                    final = {**current, '_history_keys': proposed}
                    size = len(BSON.encode(final)) + len(BSON.encode(asdict(evidence)))
                    used += size  # Include repeated attempts in the processed-byte budget.
                    if size > budgets.document_bytes or used > budgets.total_bytes or clock() >= tx_deadline:
                        raise Conflict()
                    tx.stage(bytes(BSON.encode(current)), intent.proposed_keys, evidence)
                    guard(tx)
                    if clock() >= tx_deadline:
                        raise Conflict()
                    for _commit in range(budgets.commit_attempts):
                        commits += 1
                        # Once commit was sent, failed guards/deadlines cannot prove rollback.
                        controller.pending = intent
                        try:
                            tx.commit()
                            controller.pending = None
                            confirmed += 1
                            finished = True
                            break
                        except UnknownCommit:
                            if clock() >= tx_deadline:
                                break
                    if not finished:
                        state, error = 'uncertain', 'commit_unconfirmed'
                        break
                except TransientTransaction:
                    # This exception contract explicitly proves abort, unlike UnknownCommit.
                    controller.pending = None
                finally:
                    try:
                        tx.close(min(deadline, clock() + 2))
                    except Exception:
                        controller.halted = True
                    tx = None
                if finished or controller.pending is not None or controller.halted:
                    break
            if controller.halted:
                state, error = ('uncertain', 'reconciliation_required') if controller.pending else ('blocked', 'cleanup_failure')
                break
            if controller.pending is not None:
                break
            if not finished:
                raise Conflict()
        else:
            guard(adapter)
            state = 'confirmed'  # Only approved intentions, never whole-history coverage.
    except Conflict:
        state, error = ('uncertain', 'reconciliation_required') if controller.pending else ('blocked', 'precondition_or_budget_conflict')
    except Exception:
        state, error = ('uncertain', 'reconciliation_required') if controller.pending else ('blocked', 'adapter_failure')
    finally:
        try:
            adapter.close(clock() + 2)
        except Exception:
            controller.halted = True
            state, error = ('uncertain', 'reconciliation_required') if controller.pending else ('blocked', 'cleanup_failure')
    if state == 'blocked' and confirmed + recovered:
        state = 'partial_confirmed_blocked'
    return _report(state, confirmed, recovered, error, attempts, commits, used)


def reconcile(adapter, plan, target, auth, controller, *, clock=time.monotonic):
    """Read-only fake reconciliation. Absence keeps the controller pending."""
    result = 'uncertain'
    error = 'evidence_absent'
    try:
        _authorize(plan, target, auth, clock())
        if controller.binding != (plan.run_id, plan.digest, target.binding(), auth.revision, auth.exclusion_epoch):
            raise Conflict()
        adapter.bind_controller(controller, controller.binding)
        intent = controller.pending
        if intent is None or intent not in plan.intents:
            raise Conflict()
        _observe(adapter.observe(), target, auth)
        evidence = evidence_for(plan, intent, auth)
        receipt = adapter.receipt(evidence.key)
        if receipt is not None:
            if type(receipt) is not Evidence or receipt != evidence:
                raise Conflict()
            result, error = 'original_confirmed', None
    except Exception:
        result, error = 'blocked', 'reconciliation_conflict'
    finally:
        try:
            adapter.close(clock() + 2)
        except Exception:
            result, error = 'blocked', 'cleanup_failure'
    if result == 'original_confirmed':
        controller.pending = None
    return {'state': result, 'error': error, 'offline_simulation': True,
            'coverage_complete_asserted': False, 'indexed_reads_allowed': False,
            'financial_correctness_asserted': False, 'certificate_issued': False}


def revert_policy(*args):
    return reversal_status(*args)  # No REVERT implementation, including ABA cases.
