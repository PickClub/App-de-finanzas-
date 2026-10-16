"""Experimental read-only orchestration. No client, files, secrets or DB adapter.

Every response is required to attest the pinned T and destination. A future real
adapter must verify those attestations; this module does not certify infrastructure.
"""
from dataclasses import dataclass
from collections import Counter
import time
from typing import Protocol

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.history_keys import derive_history_keys, inspect_history_keys
from backend.experiments.c3_history_diagnosis_offline import physical_key
from backend.experiments.c3_mongodb_diagnosis_design import PARTITIONS, partition_for, validate_inventory


@dataclass(frozen=True)
class Limits:
    batch_documents: int = 100
    batch_bytes: int = 1048576
    history_documents: int = 10000
    total_bytes: int = 33554432
    requests: int = 10000
    seconds: float = 30.0


@dataclass(frozen=True)
class Request:
    T: Timestamp
    binding: str
    read_concern: str
    batch_documents: int
    batch_bytes: int
    deadline: float


@dataclass(frozen=True)
class Response:
    T: Timestamp
    binding: str
    documents: tuple  # BSON encoded, not public output.
    exhausted: bool


class Reader(Protocol):
    def inventory(self, request: Request) -> Response: ...
    def page(self, request: Request, partition: int, after) -> Response: ...
    def duplicates(self, request: Request): ...  # Iterator of bounded Responses.


class StopDiagnostic(ValueError):
    pass


def bson_type(value):
    if type(value) is int:return 'int'
    if type(value) is Int64:return 'long'
    if type(value) is str:return 'string'
    if type(value) in (Binary,bytes):return 'binData'
    if type(value) is ObjectId:return 'objectId'
    raise StopDiagnostic('unsupported_physical_type')


def run_diagnosis(reader: Reader, authorization, observation, T, *, limits=Limits(), clock=time.monotonic):
    report={'state':'incompleto','complete_at_T':False,'keys_ready_at_T':False,
            'financial_correctness_asserted':False,'certificate_issued':False,'indexed_reads_allowed':False,
            'counts':{},'visited':0,'duplicate_groups':0,'extra_duplicate_documents':0,
            'source_unverifiable':0,'metrics':{'batches':0,'bson_bytes':0,'duplicate_rows':0},'error':None}
    start=clock()
    try:
        if type(T) is not Timestamp:raise StopDiagnostic('invalid_T')
        if (any(type(v) is not int or v<1 for v in (limits.batch_documents,limits.batch_bytes,
                limits.history_documents,limits.total_bytes,limits.requests))
                or type(limits.seconds) not in (int,float) or not 0<limits.seconds<=3600
                or limits.batch_documents>1000 or limits.batch_bytes>4194304):
            raise StopDiagnostic('invalid_limits')
        request=Request(T,authorization.binding(),'snapshot',limits.batch_documents,limits.batch_bytes,start+limits.seconds)
        def checkpoint():
            authorization.check('diagnose',observation)
            if clock()>=request.deadline:raise StopDiagnostic('deadline_exceeded')
        def consume(response):
            checkpoint()
            if type(response) is not Response or response.T!=T or type(response.T) is not Timestamp:
                raise StopDiagnostic('snapshot_time_mismatch')
            if response.binding!=request.binding:raise StopDiagnostic('destination_mismatch')
            if type(response.exhausted) is not bool or type(response.documents) is not tuple:
                raise StopDiagnostic('invalid_response')
            size=sum(len(x) for x in response.documents if type(x) in (bytes,BSON))
            if (len(response.documents)>limits.batch_documents or size>limits.batch_bytes
                    or any(type(x) not in (bytes,BSON) for x in response.documents)):
                raise StopDiagnostic('batch_budget_exceeded')
            report['metrics']['batches']+=1;report['metrics']['bson_bytes']+=size
            if report['metrics']['batches']>limits.requests or report['metrics']['bson_bytes']>limits.total_bytes:
                raise StopDiagnostic('total_budget_exceeded')
            if not response.documents and not response.exhausted:raise StopDiagnostic('no_progress')
            try:return [BSON(x).decode() for x in response.documents]
            except Exception:raise StopDiagnostic('invalid_bson') from None
        def fetch(method,*args):
            checkpoint();result=method(request,*args);return result,consume(result)
        inventory_response,items=fetch(reader.inventory)
        if not inventory_response.exhausted:raise StopDiagnostic('incomplete_inventory')
        inventory={}
        for item in items:
            if set(item)!={'type','count'} or item['type'] in inventory:raise StopDiagnostic('invalid_inventory')
            if type(item['count']) is not int or item['count']<=0:raise StopDiagnostic('invalid_inventory')
            inventory[item['type']]=item['count']
        try:expected=validate_inventory(inventory)
        except ValueError:raise StopDiagnostic('unsupported_physical_type') from None
        if expected>limits.history_documents:raise StopDiagnostic('document_budget_exceeded')
        observed=Counter()
        for part in range(len(PARTITIONS)):
            last=None
            while True:
                response,rows=fetch(reader.page,part,last)
                for row in rows:
                    value=row.get('_id')
                    try:
                        if partition_for(value)!=part or (last is not None and physical_key(value)<=physical_key(last)):
                            raise ValueError()
                    except ValueError:raise StopDiagnostic('unordered_or_wrong_partition') from None
                    if row.get('user_id')!=authorization.target.user_id or type(row.get('id')) is not str or not 1<=len(row['id'])<=256:
                        raise StopDiagnostic('invalid_identity')
                    observed[bson_type(value)]+=1;report['visited']+=1
                    if report['visited']>limits.history_documents or report['visited']>expected:
                        raise StopDiagnostic('document_budget_or_inventory_exceeded')
                    state=inspect_history_keys(row,authorization.generation)
                    report['counts'][state]=report['counts'].get(state,0)+1
                    report['source_unverifiable']+=derive_history_keys(row,authorization.generation)['state']=='unverifiable'
                    last=value
                if response.exhausted:break
        if dict(observed)!=inventory:raise StopDiagnostic('inventory_coverage_mismatch')
        previous=None;group_size=0;duplicate_done=False
        checkpoint()
        iterator=iter(reader.duplicates(request))
        while True:
            checkpoint()
            try:response=next(iterator)
            except StopIteration:break
            rows=consume(response)
            for row in rows:
                logical=row.get('id')
                if row.get('user_id')!=authorization.target.user_id or type(logical) is not str or not 1<=len(logical)<=256:
                    raise StopDiagnostic('invalid_duplicate_identity')
                key=(logical.encode('utf-8'),physical_key(row.get('_id')))
                if previous is not None and key<=previous:raise StopDiagnostic('unordered_duplicate_stream')
                if previous is not None and key[0]==previous[0]:
                    group_size+=1;report['extra_duplicate_documents']+=1
                    if group_size==2:report['duplicate_groups']+=1
                else:group_size=1
                previous=key;report['metrics']['duplicate_rows']+=1
                if report['metrics']['duplicate_rows']>limits.history_documents:
                    raise StopDiagnostic('document_budget_exceeded')
            if response.exhausted:
                duplicate_done=True
                # Exact protocol requires iterator end after final batch.
                checkpoint()
                try:next(iterator)
                except StopIteration:break
                raise StopDiagnostic('data_after_exhaustion')
        if not duplicate_done or report['metrics']['duplicate_rows']!=expected:
            raise StopDiagnostic('incomplete_duplicate_coverage')
        checkpoint()
        report['state']='completo_a_T';report['complete_at_T']=True
        report['keys_ready_at_T']=(set(report['counts'])<={'ready'} and not report['source_unverifiable']
                                   and not report['duplicate_groups'])
    except OperationFailure as exc:
        report['error']='snapshot_unavailable' if exc.code in (239,246) else 'cursor_lost' if exc.code==43 else 'database_read_error'
        report['state']='incompleto' if exc.code==43 else 'abortado'
    except ConnectionFailure:
        report['error']='connection_failure';report['state']='incompleto'
    except StopDiagnostic as exc:
        code=str(exc)
        allowed={'invalid_T','invalid_limits','deadline_exceeded','snapshot_time_mismatch','destination_mismatch',
                 'invalid_response','batch_budget_exceeded','total_budget_exceeded','no_progress','invalid_bson',
                 'incomplete_inventory','invalid_inventory','unsupported_physical_type','document_budget_exceeded',
                 'unordered_or_wrong_partition','invalid_identity','document_budget_or_inventory_exceeded',
                 'inventory_coverage_mismatch','invalid_duplicate_identity','unordered_duplicate_stream',
                 'data_after_exhaustion','incomplete_duplicate_coverage'}
        report['error']=code if code in allowed else 'adapter_or_validation_failure';report['state']='abortado'
    except Exception:
        report['error']='adapter_or_validation_failure';report['state']='abortado'
    finally:
        report['metrics']['elapsed_seconds']=max(0,clock()-start)
    return report
