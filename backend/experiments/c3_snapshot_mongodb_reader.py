"""Experimental Reader only; no startup/client creation, writes or production use."""
import time
from contextlib import contextmanager

from bson import BSON
from bson.timestamp import Timestamp
from pymongo import timeout
from pymongo.command_cursor import CommandCursor
from pymongo.errors import PyMongoError

from backend.financial_context import validate_metadata
from backend.experiments.c3_consistent_diagnosis_prototype import Response, StopDiagnostic
from backend.experiments.c3_mongodb_diagnosis_design import read_filter, type_inventory_pipeline, duplicate_stream_pipeline

URI='mongodb://127.0.0.1:27018/?replicaSet=app_finanzas_dev_rs&directConnection=true'


class MongoSnapshotReader:
    """Context must enclose run_diagnosis so aborts also close suspended streams.

    Owns sessions/cursors, optionally client. The caller supplies an authorized
    newly created synthetic DB, its pins and a server-selected T.
    """
    def __init__(self, client, authorization, observation, T, *, own_client=False, before_getmore=None):
        target=authorization.target
        if target.uri!=URI or not target.database.startswith('test_c3_adapter_') or type(T) is not Timestamp:
            raise ValueError('Experimental destination or T is invalid')
        self.client=client;self.auth=authorization;self.obs=observation;self.T=T
        self.db=client[target.database];self.collection=target.collection
        self.own_client=own_client;self.before_getmore=before_getmore;self.active=[];self.closed=False
        self.metrics={'initial_snapshot_commands':0,'max_initial_reply_bson_bytes':0,
                      'sessions_opened':0,'sessions_closed':0,'cursor_kills':0,'cleanup_errors':0}
        self.anchors=set()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        for handle in list(self.active):self._release(handle)
        if self.own_client:self.client.close()
        self.closed=True
    def _release(self,h):
        if h not in self.active:return
        try:
            if h.get('command_cursor') is not None:
                if h['command_cursor'].cursor_id:self.metrics['cursor_kills']+=1
                with timeout(None):h['command_cursor'].close()
            elif h['cursor']:
                with timeout(None):self.db.command({'killCursors':h['collection'],'cursors':[h['cursor']]},session=h['session'])
                self.metrics['cursor_kills']+=1
        except PyMongoError:self.metrics['cleanup_errors']+=1
        finally:
            h['session'].end_session();self.metrics['sessions_closed']+=1;self.active.remove(h)
    def _validate(self,req):
        if self.closed or req.T!=self.T or type(req.T) is not Timestamp or req.read_concern!='snapshot':
            raise StopDiagnostic('snapshot_time_mismatch')
        if req.binding!=self.auth.binding():raise StopDiagnostic('destination_mismatch')
        self.auth.check('diagnose',self.obs)
        remaining=req.deadline-time.monotonic()
        if remaining<=0:raise StopDiagnostic('deadline_exceeded')
        return remaining
    def _guard(self,req):
        remaining=self._validate(req)
        with timeout(remaining):
            if self.client.address!=('127.0.0.1',27018):raise StopDiagnostic('destination_mismatch')
            hello=self.client.admin.command('hello')
            if not hello.get('isWritablePrimary') or hello.get('setName')!='app_finanzas_dev_rs':
                raise StopDiagnostic('destination_mismatch')
            info=list(self.db.list_collections(filter={'name':self.collection}))
            if len(info)!=1 or info[0]['info']['uuid']!=self.auth.target.collection_uuid:
                raise StopDiagnostic('destination_mismatch')
            validate_metadata(self.db.moneyflow_metadata.find_one({'_id':'financial-context'}),self.auth.target.environment_id)
            with self.client.start_session(causal_consistency=False) as session:
                command={'find':'moneyflow_metadata','filter':{'_id':'financial-context'},'limit':1,'singleBatch':True,
                         'readConcern':{'level':'snapshot','atClusterTime':self.T},
                         'maxTimeMS':max(1,min(10000,int(remaining*1000)))}
                reply=self.db.command(command,session=session)
                docs=reply['cursor']['firstBatch']
                if reply['cursor']['id'] or len(docs)!=1:raise StopDiagnostic('destination_mismatch')
                validate_metadata(docs[0],self.auth.target.environment_id)
                self._attest(reply)
    def _attest(self,reply):
        if reply.get('partialResultsReturned') or reply.get('cursor',{}).get('partialResultsReturned'):
            raise StopDiagnostic('invalid_response')
        reported=reply.get('atClusterTime') or reply.get('cursor',{}).get('atClusterTime')
        if reported is not None and reported!=self.T:raise StopDiagnostic('snapshot_time_mismatch')
        self.metrics['max_initial_reply_bson_bytes']=max(self.metrics['max_initial_reply_bson_bytes'],len(BSON.encode(reply)))
    def _stream(self,req,command):
        self._guard(req)
        session=self.client.start_session(causal_consistency=False)
        h={'session':session,'cursor':0,'collection':self.collection,'T':self.T,'binding':req.binding}
        self.active.append(h);self.metrics['sessions_opened']+=1
        try:
            remaining=self._validate(req)
            initial={**command,'readConcern':{'level':'snapshot','atClusterTime':self.T},
                     'maxTimeMS':max(1,min(10000,int(remaining*1000)))}
            self.anchors.add((self.T.time,self.T.inc));self.metrics['initial_snapshot_commands']+=1
            with timeout(remaining):reply=self.db.command(initial,session=session)
            # Register cursor BEFORE validation so divergent replies still clean up.
            cursor=reply['cursor'];h['cursor']=cursor['id'];h['collection']=cursor['ns'].split('.',1)[1]
            if cursor['ns']!=self.auth.target.database+'.'+self.collection:raise StopDiagnostic('destination_mismatch')
            self._attest(reply)
            command_cursor=CommandCursor(self.db[self.collection],cursor,self.client.address,
                batch_size=min(req.batch_documents,32),session=session,explicit_session=True)
            h['command_cursor']=command_cursor
            # Controlled fault hook only for a real open server cursor.
            if self.before_getmore and command_cursor.cursor_id:self.before_getmore(self,h)
            while True:
                remaining=self._validate(req)
                # Public driver cursor uses CSOT with cmd=None for getMore. It
                # retains session/cursor context without forbidden maxTimeMS.
                try:
                    with timeout(remaining):row=next(command_cursor)
                except StopIteration:break
                yield bytes(BSON.encode(row))
        finally:self._release(h)
    def _response(self,req,docs,exhausted):return Response(self.T,req.binding,tuple(docs),exhausted)
    def inventory(self,req):
        command={'aggregate':self.collection,'pipeline':type_inventory_pipeline(self.auth.target.user_id),
                 'cursor':{'batchSize':min(req.batch_documents,32)},'allowDiskUse':False,'collation':{'locale':'simple'}}
        docs=[];size=0
        for raw in self._stream(req,command):
            row=BSON(raw).decode();encoded=bytes(BSON.encode({'type':row['_id'],'count':row['count']}))
            docs.append(encoded);size+=len(encoded)
            if len(docs)>req.batch_documents or size>req.batch_bytes:
                raise StopDiagnostic('batch_budget_exceeded')
        return self._response(req,docs,True)
    def page(self,req,partition,after):
        command={'find':self.collection,'filter':read_filter(self.auth.target.user_id,partition,after),
                 'sort':{'_id':1},'limit':req.batch_documents+1,'batchSize':min(req.batch_documents,32),
                 'projection':{'_id':1,'id':1,'user_id':1,'date':1,'amount':1,'_history_keys':1},
                 'allowDiskUse':False,'collation':{'locale':'simple'}}
        stream=self._stream(req,command);docs=[];size=0;exhausted=True
        try:
            for raw in stream:
                if len(raw)>req.batch_bytes:raise StopDiagnostic('batch_budget_exceeded')
                if len(docs)==req.batch_documents or size+len(raw)>req.batch_bytes:
                    exhausted=False;break
                docs.append(raw);size+=len(raw)
        finally:stream.close()
        return self._response(req,docs,exhausted)
    def duplicates(self,req):
        command={'aggregate':self.collection,'pipeline':duplicate_stream_pipeline(self.auth.target.user_id),
                 'cursor':{'batchSize':min(req.batch_documents,32)},'allowDiskUse':False,'collation':{'locale':'simple'}}
        stream=self._stream(req,command);docs=[];size=0
        try:
            for raw in stream:
                if len(raw)>req.batch_bytes:raise StopDiagnostic('batch_budget_exceeded')
                if docs and (len(docs)==req.batch_documents or size+len(raw)>req.batch_bytes):
                    yield self._response(req,docs,False);docs=[];size=0
                docs.append(raw);size+=len(raw)
            yield self._response(req,docs,True)
        finally:stream.close()
