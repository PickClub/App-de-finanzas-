"""Explicit read-only administrative adapter. Importing never creates a client."""
import time

from bson import BSON
from bson.timestamp import Timestamp
from pymongo import timeout
from pymongo.command_cursor import CommandCursor
from pymongo.monitoring import CommandListener

from backend.financial_context import validate_metadata
from backend.history_diagnostics import Response, StopDiagnostic, PARTITIONS, partition_for, typed_id


class SnapshotAudit(CommandListener):
    """Inspect getMore attestations without retaining commands or source documents."""
    def __init__(self, database, collection):
        self.database=database;self.collection=collection;self.T=None;self.pending=set();self.error=None
    def started(self,event):
        try:
            if event.command_name=='getMore' and event.command.get('collection')==self.collection:
                if event.database_name!=self.database:self.error='destination_mismatch'
                if len(self.pending)>=10000:self.error='total_budget_exceeded'
                else:self.pending.add(event.request_id)
        except Exception:self.error='invalid_response'
    def succeeded(self,event):
        if event.request_id not in self.pending:return
        self.pending.discard(event.request_id)
        try:
            cursor=event.reply.get('cursor',{})
            if cursor.get('ns')!=self.database+'.'+self.collection:self.error='destination_mismatch'
            if event.reply.get('partialResultsReturned') or cursor.get('partialResultsReturned'):
                self.error='invalid_response'
            observed=event.reply.get('atClusterTime') or cursor.get('atClusterTime')
            if observed is not None and observed!=self.T:self.error='snapshot_time_mismatch'
        except Exception:self.error='invalid_response'
    def failed(self,event):self.pending.discard(event.request_id)
    def check(self):
        if self.error:raise StopDiagnostic(self.error)

def read_filter(user, partition, after=None):
    if type(partition) is not int or not 0 <= partition < len(PARTITIONS):
        raise StopDiagnostic('invalid_response')
    operators = {'$type':list(PARTITIONS[partition])}
    if after is not None:
        if partition_for(after) != partition: raise StopDiagnostic('invalid_response')
        operators['$gt'] = typed_id(after)
    return {'user_id':user, '_id':operators}


def type_inventory_pipeline(user):
    return [{'$match':{'user_id':user}}, {'$group':{'_id':{'$type':'$_id'},'count':{'$sum':1}}}]


def duplicate_stream_pipeline(user):
    return [{'$match':{'user_id':user,'$expr':{'$eq':[{'$type':'$id'},'string']}}},
            {'$project':{'_id':1,'id':1,'user_id':1}}, {'$sort':{'id':1,'_id':1}}]


class MongoSnapshotReader:
    """Context must enclose run_diagnosis so aborts also close suspended streams.

    Owns sessions/cursors, optionally client. Destination pins must be independently
    approved. A completed diagnostic is not authorization to provision data.
    """
    def __init__(self, client, target, T=None, *, own_client=False, audit=None):
        target.validate()
        if T is not None and type(T) is not Timestamp: raise StopDiagnostic('invalid_T')
        self.client=client;self.target=target;self.T=T
        self.db=client[target.database];self.collection=target.collection
        self.own_client=own_client;self.active=[];self.closed=False
        self.metrics={'initial_snapshot_commands':0,'max_initial_reply_bson_bytes':0,
                      'sessions_opened':0,'sessions_closed':0,'cursor_kills':0,'cleanup_errors':0}
        self.anchors=set()
        self.audit=audit
        if self.audit and T is not None:self.audit.T=T
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
    def close(self):
        if self.closed:return
        deadline=time.monotonic()+2.0
        try:
            for handle in list(self.active):self._release(handle, deadline)
        finally:
            if self.own_client:
                try:
                    with timeout(max(.001,deadline-time.monotonic())):self.client.close()
                except Exception:self.metrics['cleanup_errors']+=1
            self.closed=True
    def _release(self,h,deadline=None):
        if h not in self.active:return
        deadline=deadline or time.monotonic()+2.0
        try:
            with timeout(max(.001,deadline-time.monotonic())):
                if h.get('command_cursor') is not None:
                    if h['command_cursor'].cursor_id:self.metrics['cursor_kills']+=1
                    h['command_cursor'].close()
                elif h['cursor']:
                    self.db.command({'killCursors':h['collection'],'cursors':[h['cursor']]},session=h['session'])
                    self.metrics['cursor_kills']+=1
        except Exception:self.metrics['cleanup_errors']+=1
        finally:
            try:
                with timeout(max(.001,deadline-time.monotonic())):h['session'].end_session()
                self.metrics['sessions_closed']+=1
            except Exception:self.metrics['cleanup_errors']+=1
            finally:self.active.remove(h)
    def _validate(self,req):
        if self.closed or req.T!=self.T or type(req.T) is not Timestamp or req.read_concern!='snapshot':
            raise StopDiagnostic('snapshot_time_mismatch')
        if req.binding!=self.target.binding():raise StopDiagnostic('destination_mismatch')
        self.target.validate()
        remaining=req.deadline-time.monotonic()
        if remaining<=0:raise StopDiagnostic('deadline_exceeded')
        return remaining
    def _identity_current(self, deadline):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise StopDiagnostic('deadline_exceeded')
        with timeout(remaining):
            if self.client.address!=('127.0.0.1',27018):raise StopDiagnostic('destination_mismatch')
            hello=self.client.admin.command('hello')
            if (not hello.get('isWritablePrimary') or hello.get('setName')!='app_finanzas_dev_rs'
                    or hello.get('logicalSessionTimeoutMinutes') is None):
                raise StopDiagnostic('destination_mismatch')
            build=self.client.admin.command('buildInfo')
            if not str(build.get('version','')).startswith('8.0.'):raise StopDiagnostic('destination_mismatch')
            with self.db.list_collections(filter={'name':self.collection}) as cursor:
                info=list(cursor)
            if len(info)!=1 or info[0].get('info',{}).get('uuid')!=self.target.collection_uuid:
                raise StopDiagnostic('destination_mismatch')
            validate_metadata(self.db.moneyflow_metadata.find_one({'_id':'financial-context'}),self.target.environment_id)

    def _initial_command(self, command, session):
        # Closed command vocabulary; pipeline is generated internally, never CLI input.
        if 'find' in command:
            if command['find'] not in (self.collection,'moneyflow_metadata'):
                raise StopDiagnostic('invalid_response')
            allowed={'find','filter','sort','limit','batchSize','singleBatch','projection','allowDiskUse','collation','readConcern','maxTimeMS'}
        elif 'aggregate' in command:
            if command['aggregate']!=self.collection:raise StopDiagnostic('invalid_response')
            allowed={'aggregate','pipeline','cursor','allowDiskUse','collation','readConcern','maxTimeMS'}
            if any(set(stage)-{'$match','$group','$project','$sort'} or len(stage)!=1 for stage in command['pipeline']):
                raise StopDiagnostic('invalid_response')
        else:raise StopDiagnostic('invalid_response')
        if set(command)-allowed or command.get('allowDiskUse',False) is not False:
            raise StopDiagnostic('invalid_response')
        return self.db.command(command,session=session)

    def _metadata_snapshot(self, deadline, *, select=False):
        remaining=deadline-time.monotonic()
        if remaining<=0:raise StopDiagnostic('deadline_exceeded')
        with timeout(remaining), self.client.start_session(causal_consistency=False) as session:
            concern={'level':'snapshot'}
            if not select:concern['atClusterTime']=self.T
            command={'find':'moneyflow_metadata','filter':{'_id':'financial-context'},'limit':1,'singleBatch':True,
                     'readConcern':concern,'maxTimeMS':max(1,min(10000,int(remaining*1000)))}
            reply=self._initial_command(command,session)
            cursor=reply.get('cursor',{})
            if cursor.get('id') or cursor.get('ns')!=self.target.database+'.moneyflow_metadata':
                raise StopDiagnostic('invalid_response')
            docs=cursor.get('firstBatch',[])
            if len(docs)!=1:raise StopDiagnostic('destination_mismatch')
            validate_metadata(docs[0],self.target.environment_id)
            if select:
                selected=reply.get('atClusterTime') or cursor.get('atClusterTime')
                if type(selected) is not Timestamp:raise StopDiagnostic('invalid_T')
                self.T=selected
                if self.audit:self.audit.T=selected
            self._attest(reply)

    def acquire_snapshot(self, deadline):
        self._identity_current(deadline)
        self._metadata_snapshot(deadline,select=True)
        self._identity_current(deadline)
        return self.T

    def _guard(self,req):
        self._validate(req)
        self._identity_current(req.deadline)
        self._metadata_snapshot(req.deadline)

    def verify_identity(self,req):
        self._guard(req)
        if self.audit:self.audit.check()
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
            with timeout(remaining):reply=self._initial_command(initial,session)
            cursor=reply['cursor']
            if cursor['ns']!=self.target.database+'.'+self.collection:
                # Never send cleanup commands to an unapproved namespace.
                self.metrics['cleanup_errors']+=1
                raise StopDiagnostic('destination_mismatch')
            # Register only authorized cursors before attesting their snapshot.
            h['cursor']=cursor['id']
            self._attest(reply)
            command_cursor=CommandCursor(self.db[self.collection],cursor,self.client.address,
                batch_size=min(req.batch_documents,32),session=session,explicit_session=True)
            h['command_cursor']=command_cursor
            while True:
                remaining=self._validate(req)
                # Public driver cursor uses CSOT with cmd=None for getMore. It
                # retains session/cursor context without forbidden maxTimeMS.
                try:
                    with timeout(remaining):row=next(command_cursor)
                except StopIteration:
                    if self.audit:self.audit.check()
                    break
                if self.audit:self.audit.check()
                yield bytes(BSON.encode(row))
        finally:self._release(h)
    def _response(self,req,docs,exhausted):return Response(self.T,req.binding,tuple(docs),exhausted)
    def inventory(self,req):
        command={'aggregate':self.collection,'pipeline':type_inventory_pipeline(self.target.user_id),
                 'cursor':{'batchSize':min(req.batch_documents,32)},'allowDiskUse':False,'collation':{'locale':'simple'}}
        docs=[];size=0
        for raw in self._stream(req,command):
            row=BSON(raw).decode();encoded=bytes(BSON.encode({'type':row['_id'],'count':row['count']}))
            docs.append(encoded);size+=len(encoded)
            if len(docs)>req.batch_documents or size>req.batch_bytes:
                raise StopDiagnostic('batch_budget_exceeded')
        return self._response(req,docs,True)
    def page(self,req,partition,after):
        command={'find':self.collection,'filter':read_filter(self.target.user_id,partition,after),
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
        command={'aggregate':self.collection,'pipeline':duplicate_stream_pipeline(self.target.user_id),
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
