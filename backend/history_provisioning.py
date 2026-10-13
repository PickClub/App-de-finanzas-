"""Offline missing-to-ready plans. No clients, storage, APPLY or REVERT."""
from dataclasses import dataclass, field
import hashlib
from uuid import UUID
import time

from bson import BSON
from bson.timestamp import Timestamp

from backend.history_diagnostics import (
    Limits, Response, Target, StopDiagnostic, physical_key, run_diagnosis,
)
from backend.history_keys import SOURCE_FIELDS, derive_history_keys, inspect_history_keys, source_fingerprint


@dataclass(frozen=True)
class Intent:
    physical_id: bytes = field(repr=False)
    source_sha256: str = field(repr=False)
    proposed_keys: bytes = field(repr=False)
    prior_field_absent: bool = True

    def digest(self):
        return hashlib.sha256(BSON.encode({'physical_id':self.physical_id,'source':self.source_sha256,
                                          'keys':self.proposed_keys,'absent':self.prior_field_absent})).hexdigest()


@dataclass(frozen=True)
class Plan:
    run_id: str
    destination_id: str
    snapshot: Timestamp | None
    version: int
    generation: int
    scope: str
    state: str
    complete_at_T: bool
    counts: tuple
    duplicate_groups: int
    source_unverifiable: int
    intents: tuple[Intent, ...] = field(repr=False)
    error: str | None
    digest: str

    @property
    def eligible_for_review(self):
        try:
            counts=dict(self.counts)
            return (self.state=='complete' and self.complete_at_T is True and type(self.snapshot) is Timestamp
                    and self.scope=='entire_effective_user' and self.duplicate_groups==0 and self.source_unverifiable==0
                    and set(counts)=={'missing','ready','stale_or_corrupt','unverifiable','incompatible'}
                    and all(type(n) is int and n>=0 for n in counts.values())
                    and not any(counts[k] for k in ('stale_or_corrupt','unverifiable','incompatible'))
                    and counts['missing']==len(self.intents) and sum(counts.values())<=Limits().history_documents
                    and self.digest==plan_digest(self))
        except Exception:return False

    @property
    def apply_authorized(self):return False

    @property
    def revert_authorized(self):return False

    def public_report(self):
        return {'run_id':self.run_id,'destination_id':self.destination_id,
                'snapshot':{'time':self.snapshot.time,'increment':self.snapshot.inc} if self.snapshot else None,
                'version':self.version,'generation':self.generation,'scope':self.scope,'state':self.state,
                'complete_at_T':self.complete_at_T,'counts':dict(self.counts),
                'candidate_count':len(self.intents),'duplicate_groups':self.duplicate_groups,
                'source_unverifiable':self.source_unverifiable,'error':self.error,'plan_digest':self.digest,
                'eligible_for_review':self.eligible_for_review,'apply_authorized':False,'revert_authorized':False,
                'financial_correctness_asserted':False,'certificate_issued':False,'indexed_reads_allowed':False}


def plan_digest(plan):
    body={'contract':1,'run_id':plan.run_id,'destination':plan.destination_id,'T':plan.snapshot,
          'version':plan.version,'generation':plan.generation,'scope':plan.scope,
          'state':plan.state,'complete_at_T':plan.complete_at_T,'counts':[list(p) for p in plan.counts],
          'duplicates':plan.duplicate_groups,'source_unverifiable':plan.source_unverifiable,
          'intents':[i.digest() for i in plan.intents],'error':plan.error}
    return hashlib.sha256(BSON.encode(body)).hexdigest()


class _Collector:
    """Observe bounded pages while canonical diagnosis proves whole-scope coverage.

    Retains only bounded plan entries, never a set of all logical IDs. Duplicate
    validation remains the global ordered-stream algorithm of run_diagnosis.
    """
    def __init__(self, reader, target, limits):
        self.reader=reader;self.target=target;self.limits=limits;self.intents=[];self.bytes=0
    def inventory(self,request):return self.reader.inventory(request)
    def duplicates(self,request):return self.reader.duplicates(request)
    def verify_identity(self,request):return self.reader.verify_identity(request)
    def page(self,request,partition,after):
        response=self.reader.page(request,partition,after)
        if (type(response) is not Response or response.T!=request.T or response.binding!=request.binding
                or type(response.documents) is not tuple or len(response.documents)>request.batch_documents):
            raise StopDiagnostic('invalid_response')
        if any(type(x) not in (bytes,BSON) for x in response.documents):raise StopDiagnostic('invalid_bson')
        if sum(len(x) for x in response.documents)>request.batch_bytes:raise StopDiagnostic('batch_budget_exceeded')
        for raw in response.documents:
            document=BSON(raw).decode()
            if '_history_keys' in document:continue
            proposed=derive_history_keys(document,self.target.generation)
            if proposed['state']!='ready':continue  # Diagnosis counts and blocks the source.
            physical_key(document.get('_id'))
            intent=Intent(bytes(BSON.encode({'value':document['_id']})),source_fingerprint(document),
                          bytes(BSON.encode({'value':proposed})))
            size=len(BSON.encode({'id':intent.physical_id,'keys':intent.proposed_keys,'source':intent.source_sha256}))
            self.bytes+=size
            if size>self.limits.batch_bytes or self.bytes>self.limits.total_bytes or len(self.intents)>=self.limits.history_documents:
                raise StopDiagnostic('total_budget_exceeded')
            self.intents.append(intent)
        return response


def build_plan(reader, target: Target, run_id, T, *, limits=Limits(), clock=time.monotonic):
    """Caller supplies a read-only offline adapter; no report can authorize APPLY.

    Readers must attest inventory, sorted physical pages and global logical-ID
    stream at exactly T. A previous report is never accepted in place of traversal.
    """
    started=clock()
    try:
        parsed=UUID(run_id)
        if parsed.version!=4 or str(parsed)!=run_id:raise ValueError()
        target.validate()
    except Exception:
        raise ValueError('invalid_plan_context') from None
    collector=_Collector(reader,target,limits)
    report=run_diagnosis(collector,target,T,limits=limits,clock=clock)
    if report['metrics']['bson_bytes']+collector.bytes>limits.total_bytes:
        report.update(complete_at_T=False,state='abortado',error='total_budget_exceeded')
    complete=report['complete_at_T']
    blocked=(report['duplicate_groups']>0 or report['source_unverifiable']>0
             or any(report['counts'].get(s,0) for s in ('stale_or_corrupt','unverifiable','incompatible')))
    state='blocked' if complete and blocked else 'complete' if complete else 'incomplete' if report['state']=='incompleto' else 'aborted'
    intents=tuple(collector.intents) if state=='complete' else ()
    plan=Plan(run_id,target.binding(),T if type(T) is Timestamp else None,target.version,target.generation,
              'entire_effective_user',state,complete,tuple(sorted(report['counts'].items())),
              report['duplicate_groups'],report['source_unverifiable'],intents,report['error'],'')
    from dataclasses import replace
    plan=replace(plan,digest=plan_digest(plan))
    if plan.complete_at_T and clock()>=started+limits.seconds:
        plan=replace(plan,state='aborted',complete_at_T=False,intents=(),error='deadline_exceeded')
        plan=replace(plan,digest=plan_digest(plan))
    return plan


def validate_intent(plan, intent, current, target):
    """Pure future-precondition check; does not prove live uniqueness or write permission."""
    try:
        if not plan.eligible_for_review:return 'invalid_plan'
        if target.binding()!=plan.destination_id:return 'context_conflict'
        if intent not in plan.intents or intent.prior_field_absent is not True:return 'intent_conflict'
        physical_key(current.get('_id'))
        if BSON.encode({'value':current['_id']})!=intent.physical_id:return 'physical_identity_conflict'
        if current.get('user_id')!=target.user_id or source_fingerprint(current)!=intent.source_sha256:return 'source_conflict'
        if '_history_keys' in current:return 'metadata_conflict'
        if BSON.encode({'value':derive_history_keys(current,target.generation)})!=intent.proposed_keys:return 'source_conflict'
        return 'preconditions_match'
    except Exception:return 'invalid_preconditions'


def classify_changes(before, after):
    """Key sources vs known administrative fields; unknown changes are not assumed safe."""
    changed={k for k in set(before)|set(after) if BSON.encode({'present':k in before,'value':before.get(k)})
             !=BSON.encode({'present':k in after,'value':after.get(k)})}
    return {'key_sources_changed':bool(changed.intersection(SOURCE_FIELDS)),
            'administrative_only':bool(changed) and changed<={'name','notes','_reference_revision'},
            'other_fields_changed':bool(changed-set(SOURCE_FIELDS)-{'name','notes','_reference_revision'})}


@dataclass(frozen=True)
class ReceiptContract:
    """Evidence supplied by a fixture, never a persisted or simulated transaction."""
    run_id: str
    destination_id: str
    plan_digest: str
    intent_digest: str
    state: str


def idempotency_status(plan, intent, receipt=None):
    if not plan.eligible_for_review or intent not in plan.intents:return 'conflict'
    if receipt is None:return 'uncertain'  # Absence never confirms rollback.
    if type(receipt) is not ReceiptContract:return 'conflict'
    expected=(plan.run_id,plan.destination_id,plan.digest,intent.digest())
    if expected!=(receipt.run_id,receipt.destination_id,receipt.plan_digest,receipt.intent_digest):return 'conflict'
    return {'confirmed':'original_confirmation','uncertain':'uncertain','conflict':'conflict'}.get(receipt.state,'conflict')


def reversal_status(*_args):
    return 'blocked_operational_writer_evidence_required'
