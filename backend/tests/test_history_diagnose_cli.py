"""CLI and MongoDB adapter with fake driver resources only. Never connects."""
from copy import deepcopy
from dataclasses import replace
import importlib
import io
import json
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from bson import BSON
from bson.timestamp import Timestamp
from pymongo.errors import ConnectionFailure, OperationFailure

from backend.history_diagnostics import Request, StopDiagnostic
from backend.history_diagnostics_mongodb import MongoSnapshotReader, SnapshotAudit
from backend.history_diagnose_cli import main
from backend.tests.test_history_diagnostics import ENV, T, target, row, physical_key, bson_type

META={'_id':'financial-context','version':1,'environment_id':ENV,'created_at':'2026-10-13T00:00:00Z'}


class Session:
    def __init__(self,client):self.client=client;self.ended=False
    def __enter__(self):return self
    def __exit__(self,*args):self.end_session()
    def end_session(self):
        self.ended=True
        if self.client.cleanup_failure:raise RuntimeError('SECRET session')


class InfoCursor:
    def __init__(self,client):self.client=client
    def __enter__(self):return self
    def __exit__(self,*args):self.client.info_closed+=1
    def __iter__(self):return iter([{'info':{'uuid':self.client.uuid}}])


class CommandCursor:
    def __init__(self,collection,info,address,**kwargs):
        self.client=collection;self.rows=iter(info['firstBatch']);self.cursor_id=info['id']
        self.session=kwargs['session'];assert kwargs['explicit_session']
    def __next__(self):
        if self.client.cursor_failure:raise self.client.cursor_failure
        return next(self.rows)
    def close(self):
        self.client.cursor_closed+=1
        self.cursor_id=0
        if self.client.cleanup_failure:raise RuntimeError('SECRET cursor')


class Client:
    address=('127.0.0.1',27018)
    def __init__(self,rows=()):
        self.rows=list(rows);self.sessions=[];self.calls=[];self.closed=False;self.info_closed=0
        self.cursor_closed=0;self.cleanup_failure=False;self.cursor_failure=None
        self.uuid=target().collection_uuid;self.env=ENV;self.replica='app_finanzas_dev_rs'
        self.partial=False;self.drift=False;self.select_T=True;self.invalid_meta=False
        self.admin=self;self.moneyflow_metadata=self
    def __getitem__(self,name):return self
    def start_session(self,**kwargs):
        assert kwargs=={'causal_consistency':False}
        session=Session(self);self.sessions.append(session);return session
    def close(self):
        self.closed=True
        if self.cleanup_failure:raise RuntimeError('SECRET client')
    def list_collections(self,filter):
        self.calls.append(('listCollections',filter,None));return InfoCursor(self)
    def find_one(self,query):
        self.calls.append(('find_metadata_current',query,None))
        return {**META,'environment_id':self.env} if not self.invalid_meta else None
    def command(self,command,session=None):
        if isinstance(command,str):
            self.calls.append((command,{},session))
            return {'isWritablePrimary':True,'setName':self.replica,'logicalSessionTimeoutMinutes':30} if command=='hello' else {'version':'8.0.32'}
        self.calls.append((next(iter(command)),deepcopy(command),session))
        if 'killCursors' in command:return {'ok':1}
        name=command.get('find',command.get('aggregate'))
        if name=='moneyflow_metadata':
            rows=[{**META,'environment_id':self.env}]
        elif 'aggregate' in command and '$group' in command['pipeline'][-1]:
            counts={}
            for x in self.rows:counts[bson_type(x['_id'])]=counts.get(bson_type(x['_id']),0)+1
            rows=[{'_id':k,'count':v} for k,v in counts.items()]
        elif 'aggregate' in command:
            rows=sorted(self.rows,key=lambda x:(x['id'].encode(),physical_key(x['_id'])))
            rows=[{k:x[k] for k in ('_id','id','user_id')} for x in rows]
        else:
            allowed=command['filter']['_id']['$type'];after=command['filter']['_id'].get('$gt')
            rows=[x for x in self.rows if bson_type(x['_id']) in allowed and (after is None or physical_key(x['_id'])>physical_key(after))]
            rows=sorted(rows,key=lambda x:physical_key(x['_id']))[:command['limit']]
        cursor={'id':0,'ns':target().database+'.'+name,'firstBatch':deepcopy(rows)}
        if self.select_T:cursor['atClusterTime']=Timestamp(101,1) if self.drift and name=='transactions' else T
        if self.partial:cursor['partialResultsReturned']=True
        return {'cursor':cursor}


def arguments(**changes):
    values={'uri':target().uri,'database':target().database,'collection':'transactions',
            'expected-collection-uuid':ENV,'expected-environment-id':ENV,
            'expected-user':'default-user','version':'1','generation':'1'}
    values.update(changes)
    result=[]
    for k,v in values.items():result+=['--'+k,v]
    return result+['--approve-diagnose']


class CliTests(unittest.TestCase):
    def execute(self,client,args=None):
        output=io.StringIO()
        with patch('backend.history_diagnostics_mongodb.CommandCursor',CommandCursor):
            code=main(arguments() if args is None else args,client_factory=lambda *a,**k:client,output=output)
        return code,json.loads(output.getvalue())

    def test_empty_complete_snapshot_and_closure(self):
        client=Client();code,report=self.execute(client)
        self.assertEqual(code,0);self.assertEqual(report['visited'],0);self.assertEqual(report['snapshot'],{'time':100,'increment':1})
        self.assertTrue(client.closed);self.assertTrue(all(s.ended for s in client.sessions))
        self.assertGreater(client.info_closed,0)

    def test_all_reads_pinned_and_read_only(self):
        client=Client([row(1),row(2,id='synthetic-1')]);code,report=self.execute(client)
        self.assertEqual(code,2);self.assertEqual(report['duplicate_groups'],1)
        for name,command,session in client.calls:
            self.assertIn(name,('hello','buildInfo','listCollections','find_metadata_current','find','aggregate','killCursors'))
            if name in ('find','aggregate'):
                concern=command['readConcern'];self.assertEqual(concern['level'],'snapshot')
                if 'atClusterTime' in concern:self.assertEqual(concern['atClusterTime'],T)
                else:self.assertEqual(command['find'],'moneyflow_metadata')
                self.assertIsNotNone(session);self.assertIs(command.get('allowDiskUse',False),False)
        self.assertTrue(all(s.ended for s in client.sessions));self.assertTrue(client.closed)

    def test_argument_rejection_never_creates_client(self):
        for args in ([],arguments(uri='mongodb://SECRET@host'),arguments(**{'expected-user':'other'}),
                     arguments(**{'expected-collection-uuid':'invalid'}),arguments(generation='0'),arguments(version='2'),
                     arguments()+['--unknown','SECRET']):
            output=io.StringIO()
            with patch('backend.history_diagnose_cli.MongoClient',side_effect=AssertionError('must not connect')):
                code=main(args,client_factory=lambda *a,**k:(_ for _ in ()).throw(AssertionError('factory called')),output=output)
            self.assertEqual(code,4);self.assertNotIn('SECRET',output.getvalue())

    def test_identity_uuid_r6_primary_destination(self):
        for field,value in [('uuid',None),('env','other'),('replica','other'),('address',('remote',27018)),('invalid_meta',True)]:
            client=Client();setattr(client,field,value);code,report=self.execute(client)
            self.assertEqual(code,4);self.assertFalse(report['complete_at_T']);self.assertTrue(client.closed)

    def test_snapshot_and_partial_results_fail(self):
        for field in ('drift','partial'):
            client=Client([row(1)]);setattr(client,field,True);code,report=self.execute(client)
            self.assertEqual(code,4);self.assertFalse(report['complete_at_T']);self.assertTrue(all(s.ended for s in client.sessions))
        client=Client();client.select_T=False;self.assertEqual(self.execute(client)[0],4)

    def test_cursor_snapshot_and_network(self):
        for error,expected in [(OperationFailure('SECRET',43),3),(OperationFailure('SECRET',239),4),(ConnectionFailure('SECRET'),3)]:
            client=Client([row(1)]);client.cursor_failure=error;code,report=self.execute(client)
            self.assertEqual(code,expected);self.assertNotIn('SECRET',json.dumps(report));self.assertTrue(client.closed)
            self.assertTrue(all(s.ended for s in client.sessions))

    def test_cleanup_failure_cannot_emit_success(self):
        client=Client([row(1)]);client.cleanup_failure=True;code,report=self.execute(client)
        self.assertEqual(code,3);self.assertFalse(report['complete_at_T']);self.assertTrue(client.closed)
        self.assertEqual(report['error'],'cleanup_failure');self.assertNotIn('SECRET',json.dumps(report))

    def test_final_identity_rechecked(self):
        client=Client([row(1)])
        class ChangedReader(MongoSnapshotReader):
            def verify_identity(self,req):
                self.client.env='other';super().verify_identity(req)
        output=io.StringIO()
        with patch('backend.history_diagnostics_mongodb.CommandCursor',CommandCursor):
            code=main(arguments(),client_factory=lambda *a,**k:client,reader_factory=ChangedReader,output=output)
        self.assertEqual(code,4);self.assertFalse(json.loads(output.getvalue())['complete_at_T'])

    def test_forbidden_commands_and_spill(self):
        client=Client();reader=MongoSnapshotReader(client,target(),T)
        for command in ({'insert':'transactions','documents':[]},{'aggregate':'transactions','pipeline':[{'$out':'x'}]},
                        {'aggregate':'transactions','pipeline':[{'$merge':'x'}]},
                        {'find':'other'}, {'find':'transactions','allowDiskUse':True}):
            with self.assertRaises(StopDiagnostic):reader._initial_command(command,None)
        self.assertFalse(client.calls)

    def test_imports_have_no_effects_or_experiment_dependencies(self):
        script="""
from unittest.mock import patch
import importlib,sys
with patch('pymongo.MongoClient',side_effect=AssertionError('connected')):
 for m in ('backend.history_diagnostics','backend.history_diagnostics_mongodb','backend.history_diagnose_cli'):
  importlib.import_module(m)
assert not any(x.startswith('backend.experiments') for x in sys.modules)
"""
        result=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_cancellation_closes_client(self):
        client=Client()
        class Cancelled(MongoSnapshotReader):
            def acquire_snapshot(self,deadline):raise KeyboardInterrupt()
        output=io.StringIO();code=main(arguments(),client_factory=lambda *a,**k:client,reader_factory=Cancelled,output=output)
        self.assertEqual(code,4);self.assertTrue(client.closed)

    def test_cleanup_is_attempted_with_finite_timeouts(self):
        from contextlib import contextmanager
        budgets=[]
        @contextmanager
        def finite_timeout(seconds):
            self.assertIsNotNone(seconds);self.assertGreater(seconds,0);budgets.append(seconds);yield
        client=Client([row(1)])
        with patch('backend.history_diagnostics_mongodb.timeout',finite_timeout):
            self.assertEqual(self.execute(client)[0],2)
        self.assertTrue(client.closed);self.assertTrue(all(s.ended for s in client.sessions))
        self.assertTrue(any(n<=2 for n in budgets))

    def test_client_closed_if_adapter_construction_fails(self):
        client=Client();output=io.StringIO()
        code=main(arguments(),client_factory=lambda *a,**k:client,
                  reader_factory=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('SECRET')),output=output)
        self.assertEqual(code,4);self.assertTrue(client.closed);self.assertNotIn('SECRET',output.getvalue())

    def test_installed_driver_getmore_timeout_regression_offline(self):
        from types import SimpleNamespace
        from pymongo import timeout
        try:
            from pymongo.synchronous.pool import Connection
        except ImportError:
            from pymongo.pool import Connection
        connection=SimpleNamespace(connect_rtt=.001,set_conn_timeout=lambda seconds:None)
        generic={'getMore':123,'collection':'transactions'}
        with timeout(1):Connection.apply_timeout(connection,None,generic)
        self.assertIn('maxTimeMS',generic)
        via_cursor={'getMore':123,'collection':'transactions'}
        with timeout(1):Connection.apply_timeout(connection,None,None)
        self.assertNotIn('maxTimeMS',via_cursor)

    def test_getmore_partial_time_and_namespace_audit(self):
        from types import SimpleNamespace
        for reply in ({'cursor':{'ns':target().database+'.transactions','partialResultsReturned':True}},
                      {'cursor':{'ns':target().database+'.transactions','atClusterTime':Timestamp(101,1)}},
                      {'cursor':{'ns':'other.transactions'}}):
            audit=SnapshotAudit(target().database,'transactions');audit.T=T
            audit.started(SimpleNamespace(command_name='getMore',command={'collection':'transactions'},database_name=target().database,request_id=1))
            audit.succeeded(SimpleNamespace(request_id=1,reply=reply))
            with self.assertRaises(StopDiagnostic):audit.check()
            self.assertFalse(audit.pending)


if __name__=='__main__':unittest.main()
