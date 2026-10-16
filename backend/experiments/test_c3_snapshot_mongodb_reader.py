"""Adapter-only offline tests; never opens a MongoDB connection."""
from dataclasses import replace
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from pymongo import timeout
from pymongo.pool import Connection
from uuid import UUID
from bson import BSON
from bson.binary import Binary
from bson.timestamp import Timestamp
from pymongo.errors import OperationFailure

from backend.experiments.c3_history_provision_contract import Target, Authorization, Observation
from backend.experiments.c3_consistent_diagnosis_prototype import Request, StopDiagnostic
from backend.experiments.c3_snapshot_mongodb_reader import MongoSnapshotReader,URI

T=Timestamp(100,1);ENV='18b1080a-3bbd-47eb-88d2-b47b8c847c62'

class Session:
    def __init__(self):self.ended=False
    def end_session(self):self.ended=True
class Client:
    address=('127.0.0.1',27018)
    def __init__(self):self.sessions=[];self.closed=False;self.db=Database()
    def __getitem__(self,n):return self.db
    def start_session(self,**kwargs):
        assert kwargs=={'causal_consistency':False}
        s=Session();self.sessions.append(s);return s
    def close(self):self.closed=True
class Database:
    def __getitem__(self,n):return self
    def __init__(self):self.calls=[];self.failure=None;self.T=T
    def command(self,c,session):
        self.calls.append((c,session))
        if 'killCursors' in c:return {'ok':1}
        if 'getMore' in c:
            if self.failure:raise self.failure
            return {'cursor':{'id':0,'ns':'test_c3_adapter_fake.transactions','nextBatch':[{'_id':2}]}}
        return {'cursor':{'id':123,'ns':'test_c3_adapter_fake.transactions','firstBatch':[{'_id':1}],'atClusterTime':self.T}}

class FakeCommandCursor:
    def __init__(self,collection,info,address,*,batch_size,session,explicit_session):
        self.db=collection;self.rows=list(info['firstBatch']);self.cursor_id=info['id'];self.session=session
    def __next__(self):
        if not self.rows and self.cursor_id:
            reply=self.db.command({'getMore':self.cursor_id,'collection':'transactions','batchSize':32},self.session)
            self.cursor_id=reply['cursor']['id'];self.rows=list(reply['cursor']['nextBatch'])
        if not self.rows:raise StopIteration
        return self.rows.pop(0)
    def close(self):
        if self.cursor_id:self.db.command({'killCursors':'transactions','cursors':[self.cursor_id]},self.session)
        self.cursor_id=0

class AdapterTests(unittest.TestCase):
    def setUp(self):
        patcher=patch('backend.experiments.c3_snapshot_mongodb_reader.CommandCursor',FakeCommandCursor)
        patcher.start();self.addCleanup(patcher.stop)
        target=Target(URI,'test_c3_adapter_fake','transactions',Binary(UUID(ENV).bytes,4),ENV)
        auth=Authorization(target,'fake','4585e5293b7466f3a58c7faf783bd8707253d8ac',1,1,('diagnose',),approved=True)
        obs=Observation(target,{'_id':'financial-context','version':1,'environment_id':ENV,'created_at':'2026-10-13T00:00:00Z'})
        self.client=Client();self.reader=MongoSnapshotReader(self.client,auth,obs,T,own_client=True)
        self.reader._guard=lambda req:self.reader._validate(req)
        self.req=Request(T,auth.binding(),'snapshot',10,10000,time.monotonic()+20)
    def test_installed_driver_csot_getmore_regression(self):
        fake=SimpleNamespace(connect_rtt=.001,set_conn_timeout=lambda seconds:None)
        manual={'getMore':123,'collection':'transactions'}
        with timeout(5):Connection.apply_timeout(fake,None,manual)
        self.assertIn('maxTimeMS',manual)
        via_cursor={'getMore':123,'collection':'transactions'}
        with timeout(5):Connection.apply_timeout(fake,None,None)
        self.assertNotIn('maxTimeMS',via_cursor)

    def test_commands_pin_T_getmore_has_no_maxTimeMS(self):
        with self.reader:
            self.assertEqual(len(list(self.reader._stream(self.req,{'find':'transactions'}))),2)
        initial=self.client.db.calls[0][0];more=self.client.db.calls[1][0]
        self.assertEqual(initial['readConcern'],{'level':'snapshot','atClusterTime':T})
        self.assertNotIn('maxTimeMS',more);self.assertNotIn('readConcern',more)
        self.assertIs(self.client.db.calls[0][1],self.client.db.calls[1][1])
        self.assertTrue(all(s.ended for s in self.client.sessions));self.assertTrue(self.client.closed)
    def test_context_exit_cleans_suspended_generator(self):
        with self.reader:
            stream=self.reader._stream(self.req,{'find':'transactions'});next(stream)
            self.assertEqual(len(self.reader.active),1)
        self.assertFalse(self.reader.active)
        self.assertTrue(any('killCursors' in c for c,s in self.client.db.calls))
        self.assertTrue(self.client.sessions[0].ended)
        stream.close()
    def test_bad_time_reply_cleanup(self):
        self.client.db.T=Timestamp(101,1)
        with self.reader:
            with self.assertRaises(StopDiagnostic):list(self.reader._stream(self.req,{'find':'transactions'}))
        self.assertTrue(self.client.sessions[0].ended);self.assertFalse(self.reader.active)
    def test_cursor_failure_cleanup(self):
        self.client.db.failure=OperationFailure('private',43)
        with self.reader:
            with self.assertRaises(OperationFailure):list(self.reader._stream(self.req,{'find':'transactions'}))
        self.assertFalse(self.reader.active);self.assertTrue(self.client.sessions[0].ended)
    def test_request_T_and_binding_checked(self):
        for request in (replace(self.req,T=Timestamp(99,1)),replace(self.req,binding='other'),replace(self.req,read_concern='majority')):
            with self.assertRaises(StopDiagnostic):self.reader._validate(request)
    def test_deadline_enforced(self):
        with self.assertRaises(StopDiagnostic):self.reader._validate(replace(self.req,deadline=time.monotonic()-1))
    def test_page_byte_lookahead_does_not_skip(self):
        rows=[bytes(BSON.encode({'_id':i,'id':'synthetic'})) for i in range(4)]
        self.reader._stream=lambda req,command:iter(rows)
        # Wrapper uses generator close; use a real generator for simulated stream.
        self.reader._stream=lambda req,command:(r for r in rows)
        response=self.reader.page(replace(self.req,batch_bytes=len(rows[0])*2),0,None)
        self.assertEqual(len(response.documents),2);self.assertFalse(response.exhausted)
    def test_oversize_rejected(self):
        self.reader._stream=lambda req,command:(r for r in [BSON.encode({'padding':'x'*1000})])
        with self.assertRaises(StopDiagnostic):self.reader.page(replace(self.req,batch_bytes=10),0,None)
    def test_duplicates_final_batch_and_empty(self):
        self.reader._stream=lambda req,command:(r for r in [BSON.encode({'id':str(i)}) for i in range(3)])
        responses=list(self.reader.duplicates(replace(self.req,batch_documents=2)))
        self.assertEqual([len(r.documents) for r in responses],[2,1])
        self.assertEqual([r.exhausted for r in responses],[False,True])
        self.reader._stream=lambda req,command:(r for r in [])
        responses=list(self.reader.duplicates(self.req));self.assertEqual(responses[0].documents,());self.assertTrue(responses[0].exhausted)
    def test_partial_results_rejected(self):
        with self.assertRaises(StopDiagnostic):self.reader._attest({'partialResultsReturned':True})

if __name__=='__main__':unittest.main()
