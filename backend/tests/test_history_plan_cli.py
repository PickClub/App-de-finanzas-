"""Operational PLAN exercised with fake driver resources; no MongoDB connection."""
from dataclasses import replace
import io
import json
import subprocess
import sys
import unittest
from unittest.mock import patch

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.history_keys import derive_history_keys
from backend.history_diagnostics import Limits
from backend.history_diagnostics_mongodb import MongoSnapshotReader
from backend.history_plan_cli import main
from backend.tests.test_history_diagnose_cli import Client, CommandCursor, arguments as diagnose_arguments
from backend.tests.test_history_diagnostics import T, row

RUN = '8fba08ac-2f44-4d4c-bca2-c3589b13119e'


def arguments(**changes):
    return [a for a in diagnose_arguments(**changes) if a != '--approve-diagnose'] + ['--run-id', RUN, '--approve-plan']


class PlanCliTests(unittest.TestCase):
    def execute(self, client, args=None, reader_factory=MongoSnapshotReader):
        output = io.StringIO()
        with patch('backend.history_diagnostics_mongodb.CommandCursor', CommandCursor):
            code = main(arguments() if args is None else args, client_factory=lambda *a, **k: client,
                        reader_factory=reader_factory, output=output)
        self.assertTrue(client.closed)
        self.assertTrue(all(s.ended for s in client.sessions))
        return code, json.loads(output.getvalue())

    def test_verified_empty(self):
        code, report = self.execute(Client())
        self.assertEqual(code, 0)
        self.assertEqual(report['state'], 'complete_without_candidates')
        self.assertTrue(report['complete_at_T'])
        self.assertEqual(report['candidate_count'], 0)
        self.assertEqual(report['snapshot'], {'time': T.time, 'increment': T.inc})

    def test_missing_ready_candidates_and_existing_ready(self):
        ready = row(1); ready['_history_keys'] = derive_history_keys(ready, 1)
        client = Client([ready, row(2)])
        before = [BSON.encode(x) for x in client.rows]
        code, report = self.execute(client)
        self.assertEqual(code, 0)
        self.assertEqual(report['state'], 'complete_with_candidates')
        self.assertEqual(report['candidate_count'], 1)
        self.assertEqual(report['counts']['ready'], 1)
        self.assertEqual(before, [BSON.encode(x) for x in client.rows])

    def test_every_state_blocks_and_discards_all_candidates(self):
        ready = row(1); ready['_history_keys'] = derive_history_keys(ready, 1)
        stale = row(2); stale['_history_keys'] = derive_history_keys(stale, 1); stale['amount'] = '99'
        invalid = row(3, date='bad'); invalid['_history_keys'] = derive_history_keys(invalid, 1)
        incompatible = row(4); incompatible['_history_keys'] = derive_history_keys(incompatible, 2)
        code, report = self.execute(Client([ready, stale, invalid, incompatible, row(5), row(6, _history_keys=None)]))
        self.assertEqual(code, 2); self.assertEqual(report['state'], 'blocked')
        self.assertTrue(report['complete_at_T']); self.assertEqual(report['candidate_count'], 0)
        self.assertEqual(report['counts'], {'ready':1, 'missing':1, 'stale_or_corrupt':1, 'unverifiable':1, 'incompatible':2})

    def test_duplicates_between_batches_dates(self):
        client = Client([row(i, id='same', date=f'2026-10-{i % 28 + 1:02d}') for i in range(205)])
        code, report = self.execute(client)
        self.assertEqual(code, 2); self.assertEqual(report['duplicate_groups'], 1)
        self.assertEqual(report['candidate_count'], 0)

    def test_mixed_physical_bson(self):
        rows = [row(i, _id=value) for i, value in enumerate([1, Int64(2), 's', Binary(b'a',1), ObjectId()])]
        code, report = self.execute(Client(rows))
        self.assertEqual(code, 0); self.assertEqual(report['candidate_count'], 5)

    def test_all_snapshot_commands_same_T_and_no_writes(self):
        client = Client([row(1)])
        self.assertEqual(self.execute(client)[0], 0)
        for name, command, session in client.calls:
            self.assertIn(name, ('hello','buildInfo','listCollections','find_metadata_current','find','aggregate','killCursors'))
            if name in ('find', 'aggregate'):
                self.assertEqual(command['readConcern']['level'], 'snapshot')
                if 'atClusterTime' in command['readConcern']:
                    self.assertEqual(command['readConcern']['atClusterTime'], T)
                else:
                    self.assertEqual(command['find'], 'moneyflow_metadata')
                self.assertIs(command.get('allowDiskUse',False), False)
                self.assertIsNotNone(session)

    def test_context_changes_abort(self):
        for field, value in [('env','other'),('uuid',None),('replica','other'),('address',('remote',27018))]:
            client = Client([row(1)]); setattr(client, field, value)
            code, report = self.execute(client)
            self.assertEqual(code, 4); self.assertFalse(report['complete_at_T'])
        class FinalMismatch(MongoSnapshotReader):
            def verify_identity(self, req):
                self.client.env = 'other'; super().verify_identity(req)
        self.assertEqual(self.execute(Client([row(1)]), reader_factory=FinalMismatch)[0], 4)

    def test_versions_generations_and_approval_before_factory(self):
        for args in (arguments(version='2'), arguments(generation='0'), arguments(**{'expected-user':'other'}),
                     arguments(uri='mongodb://SECRET@host'), arguments()[:-1],
                     arguments()+['--unknown','SECRET']):
            output = io.StringIO()
            code = main(args, client_factory=lambda *a,**k: self.fail('Client created before approval'), output=output)
            self.assertEqual(code, 4); self.assertNotIn('SECRET', output.getvalue())
        self.assertEqual(self.execute(Client([row(1)]), arguments(generation='2'))[0], 0)

    def test_partial_and_snapshot_divergence(self):
        for field in ('partial', 'drift'):
            client=Client([row(1)]); setattr(client,field,True)
            code,report=self.execute(client)
            self.assertEqual(code,4); self.assertEqual(report['candidate_count'],0)
        client=Client();client.select_T=False
        self.assertEqual(self.execute(client)[0],4)

    def test_cursor_snapshot_and_connection_failures(self):
        for error, expected in [(OperationFailure('SECRET',43),3),(OperationFailure('SECRET',239),4),
                                (OperationFailure('SECRET',246),4),(ConnectionFailure('SECRET'),3)]:
            client=Client([row(1)]);client.cursor_failure=error
            code,report=self.execute(client)
            self.assertEqual(code,expected);self.assertFalse(report['complete_at_T'])
            self.assertEqual(report['candidate_count'],0);self.assertNotIn('SECRET',json.dumps(report))

    def test_resource_limits_and_duration_abort(self):
        for limits in (replace(Limits(),history_documents=1),replace(Limits(),batch_bytes=1),
                       replace(Limits(),total_bytes=1),replace(Limits(),requests=1)):
            with patch('backend.history_plan_cli.Limits',return_value=limits):
                code,report=self.execute(Client([row(1),row(2)]))
            self.assertEqual(code,4);self.assertFalse(report['complete_at_T']);self.assertEqual(report['candidate_count'],0)
        class Delayed(MongoSnapshotReader):
            def acquire_snapshot(self, deadline):
                self.T=T
                return T
        from itertools import chain, repeat
        ticks=chain([0],repeat(31))
        with patch('backend.history_plan_cli.time.monotonic',side_effect=lambda:next(ticks)):
            code,report=self.execute(Client(),reader_factory=Delayed)
        self.assertEqual(code,4);self.assertFalse(report['complete_at_T'])

    def test_digest_determinism_and_context_binding(self):
        a=self.execute(Client([row(1),row(2)]))[1]
        b=self.execute(Client([row(2),row(1)]))[1]
        self.assertEqual(a['plan_digest'],b['plan_digest'])
        c=self.execute(Client([row(1),row(2)]),arguments(generation='2'))[1]
        self.assertNotEqual(a['plan_digest'],c['plan_digest'])

    def test_cleanup_failure_invalidates_digest_and_candidates(self):
        client=Client([row(1)]);client.cleanup_failure=True
        code,report=self.execute(client)
        self.assertEqual(code,3);self.assertEqual(report['candidate_count'],0)
        self.assertIsNone(report['plan_digest']);self.assertFalse(report['eligible_for_review'])
        self.assertNotIn('SECRET',json.dumps(report))

    def test_construction_failure_and_cancel_cleanup(self):
        def broken(*a,**k):raise RuntimeError('SECRET')
        code,report=self.execute(Client(),reader_factory=broken)
        self.assertEqual(code,4);self.assertNotIn('SECRET',json.dumps(report))
        class Cancelled(MongoSnapshotReader):
            def acquire_snapshot(self,deadline):raise KeyboardInterrupt()
        self.assertEqual(self.execute(Client(),reader_factory=Cancelled)[0],4)

    def test_public_privacy_and_no_apply(self):
        code,report=self.execute(Client([row(1)]))
        encoded=json.dumps(report)
        for private in ('synthetic-1','70.123','2026-W40','mongodb://','physical_id','source_sha256','proposed_keys'):
            self.assertNotIn(private,encoded)
        for flag in ('apply_authorized','revert_authorized','financial_correctness_asserted','certificate_issued','indexed_reads_allowed'):
            self.assertIs(report[flag],False)

    def test_unsupported_bson_inventory_aborts(self):
        from backend.history_diagnostics import Response
        class Unsupported(MongoSnapshotReader):
            def inventory(self, req):
                return Response(req.T,req.binding,(bytes(BSON.encode({'type':'double','count':1})),),True)
        code,report=self.execute(Client(),reader_factory=Unsupported)
        self.assertEqual(code,4);self.assertEqual(report['error'],'unsupported_physical_type')
        self.assertFalse(report['complete_at_T']);self.assertEqual(report['candidate_count'],0)

    def test_incomplete_coverage_and_no_progress(self):
        class MissingPage(MongoSnapshotReader):
            def page(self,req,part,after):
                return self._response(req,[],True)
        code,report=self.execute(Client([row(1)]),reader_factory=MissingPage)
        self.assertEqual(code,4);self.assertFalse(report['complete_at_T']);self.assertEqual(report['candidate_count'],0)
        class NoProgress(MongoSnapshotReader):
            def page(self,req,part,after):
                return self._response(req,[],False)
        self.assertEqual(self.execute(Client([row(1)]),reader_factory=NoProgress)[0],4)

    def test_network_during_acquisition_closes_resources(self):
        class Disconnected(MongoSnapshotReader):
            def acquire_snapshot(self,deadline):raise ConnectionFailure('SECRET')
        code,report=self.execute(Client(),reader_factory=Disconnected)
        self.assertEqual(code,3);self.assertEqual(report['state'],'incomplete')
        self.assertNotIn('SECRET',json.dumps(report))

    def test_scope_and_run_cannot_be_changed_or_autoapproved(self):
        for args in (arguments()+['--scope','first-page'],arguments()+['--run-id','SECRET'],
                     arguments(**{'expected-environment-id':'SECRET'})):
            output=io.StringIO()
            code=main(args,client_factory=lambda *a,**k:self.fail('Unexpected client'),output=output)
            self.assertEqual(code,4);self.assertNotIn('SECRET',output.getvalue())

    def test_import_no_connections_no_files_no_experiments(self):
        script="""
from unittest.mock import patch
import sys
with patch('pymongo.MongoClient',side_effect=AssertionError('connection')), patch('builtins.open',side_effect=AssertionError('file')):
 import backend.history_plan_cli
assert not any(n.startswith('backend.experiments') for n in sys.modules)
"""
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':unittest.main()
