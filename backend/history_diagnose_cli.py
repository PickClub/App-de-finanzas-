"""Explicit administrative CLI. No dotenv, startup clients or public endpoints."""
import argparse
from dataclasses import replace
import json
import sys
import time
from uuid import UUID

from bson.binary import Binary
from bson.timestamp import Timestamp
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.history_diagnostics import Target, Limits, StopDiagnostic, run_diagnosis, exit_code
from backend.history_diagnostics_mongodb import MongoSnapshotReader, SnapshotAudit


class SafeParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's original error may contain URI/unknown sensitive arguments.
        raise ValueError('invalid_arguments')


def parser():
    result = SafeParser(description='Read-only historical key diagnosis; never certifies financial correctness.')
    for name in ('uri','database','collection','expected-collection-uuid','expected-environment-id','expected-user'):
        result.add_argument('--'+name, required=True)
    result.add_argument('--version', type=int, required=True)
    result.add_argument('--generation', type=int, required=True)
    result.add_argument('--approve-diagnose', action='store_true', required=True)
    return result


def failure(code):
    return {'state':'abortado','snapshot':None,'version':None,'generation':None,'destination_id':None,
            'complete_at_T':False,'keys_ready_at_T':False,'counts':{},'visited':0,'duplicate_groups':0,
            'financial_correctness_asserted':False,'certificate_issued':False,'indexed_reads_allowed':False,
            'metrics':{},'error':code}


def main(argv=None, *, client_factory=MongoClient, reader_factory=MongoSnapshotReader, output=None):
    output = sys.stdout if output is None else output
    reader = None
    client = None
    report = failure('invalid_arguments')
    context = {}
    started = time.monotonic()
    try:
        args = parser().parse_args(argv)
        uid = UUID(args.expected_collection_uuid)
        if str(uid) != args.expected_collection_uuid:raise ValueError('invalid_arguments')
        target = Target(args.uri,args.database,args.collection,Binary(uid.bytes,4),
                        args.expected_environment_id,args.expected_user,args.version,args.generation,args.approve_diagnose)
        target.validate()
        context = {'version':target.version,'generation':target.generation,'destination_id':target.binding()}
        # Creation is explicit and lazy; preflight observes no financial documents.
        audit=SnapshotAudit(target.database,target.collection)
        client = client_factory(target.uri, connect=False, retryReads=False, event_listeners=[audit],
                                serverSelectionTimeoutMS=3000,connectTimeoutMS=3000,socketTimeoutMS=10000)
        reader = reader_factory(client,target,own_client=True,audit=audit)
        deadline = started + Limits().seconds
        T = reader.acquire_snapshot(deadline)
        remaining = deadline-time.monotonic()
        if remaining <= 0:raise StopDiagnostic('deadline_exceeded')
        report = run_diagnosis(reader,target,T,limits=replace(Limits(),seconds=remaining))
    except (ValueError, StopDiagnostic):
        report = failure('invalid_arguments' if reader is None else 'identity_or_snapshot_failure')
    except OperationFailure as error:
        report = failure('snapshot_unavailable' if error.code in (239,246) else 'cursor_lost' if error.code==43 else 'database_read_error')
        if error.code==43:report['state']='incompleto'
    except ConnectionFailure:
        report = failure('connection_failure');report['state']='incompleto'
    except KeyboardInterrupt:
        report = failure('cancelled')
    except Exception:
        report = failure('administrative_read_failure')
    finally:
        report.update(context)
        if reader is not None and type(reader.T) is Timestamp and report['snapshot'] is None:
            report['snapshot']={'time':reader.T.time,'increment':reader.T.inc}
        cleanup_failed = False
        if reader is not None:
            try:
                reader.close()
                cleanup_failed = bool(reader.metrics.get('cleanup_errors'))
                report['metrics']['adapter'] = dict(reader.metrics)
            except Exception:cleanup_failed=True
        elif client is not None:
            try:
                from pymongo import timeout
                with timeout(2):client.close()
            except Exception:cleanup_failed=True
        if cleanup_failed:
            report.update(state='incompleto',complete_at_T=False,keys_ready_at_T=False,error='cleanup_failure')
        report['metrics']['total_elapsed_seconds'] = max(0,time.monotonic()-started)
    print(json.dumps(report,sort_keys=True,allow_nan=False),file=output)
    return exit_code(report)


if __name__ == '__main__':
    raise SystemExit(main())
