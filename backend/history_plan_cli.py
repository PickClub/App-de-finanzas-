"""Explicit read-only PLAN entry point. Importing never opens a client or file."""
from dataclasses import replace
import json
import sys
import time
from uuid import UUID

from bson.binary import Binary
from bson.timestamp import Timestamp
from pymongo import MongoClient, timeout
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.history_diagnose_cli import SafeParser
from backend.history_diagnostics import Target, Limits, StopDiagnostic
from backend.history_diagnostics_mongodb import MongoSnapshotReader, SnapshotAudit
from backend.history_provisioning import build_plan


def parser():
    result = SafeParser(description='Read-only historical key PLAN; never authorizes APPLY.')
    for name in ('uri', 'database', 'collection', 'expected-collection-uuid',
                 'expected-environment-id', 'expected-user', 'run-id'):
        result.add_argument('--' + name, required=True)
    result.add_argument('--version', type=int, required=True)
    result.add_argument('--generation', type=int, required=True)
    result.add_argument('--approve-plan', action='store_true', required=True)
    return result


def failure(error, state='aborted'):
    return {'state': state, 'complete_at_T': False, 'snapshot': None,
            'run_id': None, 'destination_id': None, 'version': None, 'generation': None,
            'scope': 'entire_effective_user', 'counts': {}, 'candidate_count': 0,
            'duplicate_groups': 0, 'source_unverifiable': 0, 'plan_digest': None,
            'eligible_for_review': False, 'apply_authorized': False, 'revert_authorized': False,
            'financial_correctness_asserted': False, 'certificate_issued': False,
            'indexed_reads_allowed': False, 'error': error, 'metrics': {}}


def result_code(report):
    if report['state'] in ('complete_without_candidates', 'complete_with_candidates'):
        return 0
    if report['state'] == 'blocked':
        return 2
    return 3 if report['state'] == 'incomplete' else 4


def main(argv=None, *, client_factory=MongoClient, reader_factory=MongoSnapshotReader, output=None):
    """One explicit execution; only aggregate JSON escapes this resource scope.

    Private intents remain transient. There is no persistence or APPLY handoff.
    Factories are injectable for offline tests; default execution requires approval.
    """
    output = sys.stdout if output is None else output
    reader = client = plan = None
    report = failure('invalid_arguments')
    context = {}
    started = time.monotonic()
    deadline = started + Limits().seconds
    try:
        args = parser().parse_args(argv)
        uid = UUID(args.expected_collection_uuid)
        run = UUID(args.run_id)
        if str(uid) != args.expected_collection_uuid or run.version != 4 or str(run) != args.run_id:
            raise ValueError('invalid_arguments')
        target = Target(args.uri, args.database, args.collection, Binary(uid.bytes, 4),
                        args.expected_environment_id, args.expected_user, args.version,
                        args.generation, args.approve_plan)
        target.validate()
        context = {'run_id': args.run_id, 'destination_id': target.binding(),
                   'version': target.version, 'generation': target.generation}
        audit = SnapshotAudit(target.database, target.collection)
        client = client_factory(target.uri, connect=False, retryReads=False, event_listeners=[audit],
                                serverSelectionTimeoutMS=3000, connectTimeoutMS=3000, socketTimeoutMS=10000)
        reader = reader_factory(client, target, own_client=True, audit=audit)
        T = reader.acquire_snapshot(deadline)
        if type(T) is not Timestamp or reader.T != T:
            raise StopDiagnostic('invalid_T')
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise StopDiagnostic('deadline_exceeded')
        plan = build_plan(reader, target, args.run_id, T,
                          limits=replace(Limits(), seconds=remaining))
        report = plan.public_report()
        report['metrics'] = {}
        if plan.state == 'complete':
            if not plan.eligible_for_review:
                raise StopDiagnostic('invalid_plan')
            report['state'] = 'complete_with_candidates' if plan.intents else 'complete_without_candidates'
        if time.monotonic() >= deadline:
            raise StopDiagnostic('deadline_exceeded')
    except StopDiagnostic:
        report = failure('identity_snapshot_or_protocol_failure')
    except ValueError:
        report = failure('invalid_arguments')
    except OperationFailure as error:
        report = failure('cursor_lost' if error.code == 43 else
                         'snapshot_unavailable' if error.code in (239, 246) else 'database_read_error',
                         'incomplete' if error.code == 43 else 'aborted')
    except ConnectionFailure:
        report = failure('connection_failure', 'incomplete')
    except KeyboardInterrupt:
        report = failure('cancelled')
    except Exception:
        report = failure('administrative_read_failure')
    finally:
        report.update(context)
        if reader is not None and type(reader.T) is Timestamp and report['snapshot'] is None:
            report['snapshot'] = {'time': reader.T.time, 'increment': reader.T.inc}
        cleanup_failed = False
        if reader is not None:
            try:
                reader.close()
                cleanup_failed = bool(reader.metrics.get('cleanup_errors'))
                # Only fixed aggregate metrics from the registered adapter.
                allowed = ('initial_snapshot_commands', 'max_initial_reply_bson_bytes',
                           'sessions_opened', 'sessions_closed', 'cursor_kills', 'cleanup_errors')
                report['metrics']['adapter'] = {k: reader.metrics[k] for k in allowed if k in reader.metrics}
            except Exception:
                cleanup_failed = True
        elif client is not None:
            try:
                with timeout(2):
                    client.close()
            except Exception:
                cleanup_failed = True
        if cleanup_failed:
            snapshot = report['snapshot']
            report = failure('cleanup_failure', 'incomplete')
            report.update(context, snapshot=snapshot)
        plan = None  # Never retain a usable plan after returning, including failed cleanup.
        report['metrics']['total_elapsed_seconds'] = max(0, time.monotonic() - started)
    print(json.dumps(report, sort_keys=True, allow_nan=False), file=output)
    return result_code(report)


if __name__ == '__main__':
    raise SystemExit(main())
