"""Fake driver only: no client construction, sockets, MongoDB or filesystem writes."""
from copy import deepcopy
from dataclasses import replace, asdict
import json
import subprocess
import sys
import time
import unittest
from types import SimpleNamespace

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from pymongo.errors import OperationFailure, ConnectionFailure, DuplicateKeyError

from backend.history_apply import (Authorization, Observation, RunState, apply_plan, reconcile,
                                  evidence_for, Budgets, Conflict)
from backend.history_apply_mongodb import SyntheticPermit, SyntheticMongoApplyAdapter, JOURNAL, MARKER, cas_filter
from backend.history_provisioning import build_plan
from backend.tests.test_history_diagnostics import Reader, target, row, T, ENV

NONCE='a'*32
JUUID=Binary(b'j'*16,4)
RUN='8fba08ac-2f44-4d4c-bca2-c3589b13119e'


class Verifier:
    def __init__(self,t):self.value=Observation(t,'external-epoch',True,True,True,True,0);self.calls=0
    def verify(self,permit,deadline):self.calls+=1;return self.value


class Info:
    def __init__(self,client,name):self.client=client;self.name=name
    def __enter__(self):return self
    def __exit__(self,*args):self.client.info_closed+=1
    def __iter__(self):return iter([{'info':{'uuid':self.client.uuids[self.name]}}])


class Collection:
    def __init__(self,client,name):self.client=client;self.name=name
    def with_options(self,**kwargs):self.client.options.append((self.name,kwargs));return self
    def find_one(self,query,session=None):
        self.client.calls.append(('find',self.name,deepcopy(query),session))
        if self.client.read_error:raise self.client.read_error
        rows=(session.snapshot if session else self.client.docs)[self.name]
        for document in rows:
            if document['_id']==query['_id'] and ('user_id' not in query or document.get('user_id')==query['user_id']):
                return deepcopy(document)
        return None
    def insert_one(self,record,session=None):
        self.client.calls.append(('insert',self.name,deepcopy(record),session))
        if self.client.insert_error and session:raise self.client.insert_error
        rows=(session.snapshot if session else self.client.docs)[self.name]
        if any(d['_id']==record['_id'] for d in rows):raise DuplicateKeyError('SECRET')
        rows.append(deepcopy(record))
        return SimpleNamespace(acknowledged=not self.client.unacknowledged)
    def update_one(self,query,update,upsert,session):
        self.client.calls.append(('update',self.name,(deepcopy(query),deepcopy(update),upsert),session))
        assert self.name=='transactions' and upsert is False
        assert set(update)=={'$set'} and set(update['$set'])=={'_history_keys'}
        if self.client.update_error:raise self.client.update_error
        if self.client.cas_zero:return SimpleNamespace(acknowledged=True,matched_count=0,modified_count=0)
        for document in session.snapshot[self.name]:
            if document['_id']==query['_id'] and '_history_keys' not in document:
                document.update(deepcopy(update['$set']))
                return SimpleNamespace(acknowledged=True,matched_count=1,modified_count=1)
        return SimpleNamespace(acknowledged=True,matched_count=0,modified_count=0)


class Session:
    def __init__(self,client):self.client=client;self.in_transaction=False;self.ended=False;self.commits=0;self.aborts=0
    def start_transaction(self,**kwargs):
        self.client.tx_options.append(kwargs);self.in_transaction=True
        self.snapshot=deepcopy(self.client.docs);self.original=deepcopy(self.client.docs)
    def commit_transaction(self):
        self.commits+=1
        error=self.client.commit_errors.pop(0) if self.client.commit_errors else None
        if error=='after':
            self.client.docs=deepcopy(self.snapshot);self.in_transaction=False
            raise OperationFailure('SECRET',details={'errorLabels':['UnknownTransactionCommitResult']})
        if error:
            self.in_transaction=False
            raise error
        if self.in_transaction:
            if self.client.docs!=self.original:
                self.in_transaction=False
                raise OperationFailure('SECRET',details={'errorLabels':['TransientTransactionError']})
            self.client.docs=deepcopy(self.snapshot)
        self.in_transaction=False
    def abort_transaction(self):self.aborts+=1;self.in_transaction=False
    def end_session(self):
        self.ended=True
        if self.client.cleanup_error:raise RuntimeError('SECRET')


class Client:
    address=('127.0.0.1',27018)
    def __init__(self,rows,t):
        self.docs={'transactions':deepcopy(rows),JOURNAL:[], 'moneyflow_metadata':[
            {'_id':'financial-context','version':1,'environment_id':ENV,'created_at':'2026-10-13T00:00:00Z'},
            {'_id':MARKER,'mode':'synthetic_only','nonce':NONCE,'collection_uuid':t.collection_uuid,
             'journal_uuid':JUUID,'environment_id':ENV}]}
        self.uuids={'transactions':t.collection_uuid,JOURNAL:JUUID}
        self.calls=[];self.options=[];self.sessions=[];self.tx_options=[];self.info_closed=0;self.closed=False
        self.admin=self;self.primary=True;self.replica='app_finanzas_dev_rs'
        self.commit_errors=[];self.insert_error=None;self.update_error=None;self.read_error=None
        self.cas_zero=False;self.cleanup_error=False;self.unacknowledged=False
    def __getitem__(self,name):
        if name in self.docs:return Collection(self,name)
        assert name=='test_c3_apply_'+NONCE
        return self
    def list_collections(self,filter):
        self.calls.append(('listCollections',filter['name'],{},None));return Info(self,filter['name'])
    def command(self,name):
        self.calls.append((name,'admin',{},None))
        if name=='hello':return {'isWritablePrimary':self.primary,'setName':self.replica,'logicalSessionTimeoutMinutes':30}
        assert name=='buildInfo';return {'version':'8.0.32'}
    def start_session(self,**kwargs):
        assert kwargs=={'causal_consistency':False}
        s=Session(self);self.sessions.append(s);return s
    def close(self):self.closed=True


class AdapterTests(unittest.TestCase):
    def test_legacy_profile_rejects_non_fixture_client(self):
        c,p,a,permit,v,adapter,controller=self.case()
        with self.assertRaises(Conflict):
            SyntheticMongoApplyAdapter(SimpleNamespace(),p,permit,v)
    def case(self,rows=None):
        rows=[row(1)] if rows is None else rows
        t=replace(target(),database='test_c3_apply_'+NONCE)
        p=build_plan(Reader(rows),t,RUN,T)
        a=Authorization(RUN,p.digest,t,p.scope,'b'*40,'external-epoch',time.monotonic()+100,True)
        permit=SyntheticPermit(a,NONCE,JUUID,True,True)
        client=Client(rows,t);v=Verifier(t)
        adapter=SyntheticMongoApplyAdapter(client,p,permit,v)
        return client,p,a,permit,v,adapter,RunState()
    def execute(self,c,p,a,permit,v,adapter,controller):
        report=apply_plan(adapter,p,a.target,a,controller)
        self.assertTrue(c.closed)
        self.assertTrue(all(s.ended for s in c.sessions))
        return report
    def test_compatible_atomic_and_sources_unchanged(self):
        items=self.case();c,p,a,permit,v,adapter,controller=items
        before=deepcopy(c.docs['transactions'])
        r=self.execute(*items);self.assertEqual(r['state'],'confirmed')
        self.assertEqual({k:val for k,val in c.docs['transactions'][0].items() if k!='_history_keys'},before[0])
        receipts=[d for d in c.docs[JOURNAL] if d['_id'].startswith('receipt:')]
        self.assertEqual(len(receipts),1)
        update=next(x for x in c.calls if x[0]=='update');receipt=next(x for x in c.calls if x[0]=='insert' and x[3])
        self.assertIs(update[3],receipt[3]);self.assertFalse(update[2][2])
        self.assertEqual(c.tx_options[0]['read_concern'].level,'snapshot')
        self.assertEqual(c.tx_options[0]['write_concern'].document,{'w':'majority'})
        self.assertNotIn('atClusterTime',c.tx_options[0])
    def test_constructor_pure_and_synthetic_restriction(self):
        c,p,a,permit,v,adapter,state=self.case();self.assertFalse(c.calls)
        for grant in (replace(permit,mode='real'),replace(permit,approved=False),
                      replace(permit,absence_independently_attested=False),replace(permit,nonce='other')):
            with self.assertRaises(Conflict):SyntheticMongoApplyAdapter(c,p,grant,v)
        with self.assertRaises(Conflict):SyntheticMongoApplyAdapter(c,p.public_report(),permit,v)
        with self.assertRaises(Conflict):SyntheticMongoApplyAdapter(c,p,permit,None)
        self.assertFalse(c.calls)
    def test_external_exclusion_required_before_registry_write(self):
        for changes in ({'writers_excluded':False},{'ddl_excluded':False},{'metadata_stable':False},
                        {'uniqueness_complete':False},{'duplicate_groups':1}):
            items=self.case();c,p,a,permit,v,adapter,state=items
            v.value=replace(v.value,**changes)
            self.assertEqual(self.execute(*items)['state'],'blocked')
            self.assertFalse([x for x in c.calls if x[0] in ('insert','update')])
    def test_primary_uuid_r6_marker(self):
        for change in ('primary','uuid','journal_uuid','r6','marker','destination','replica'):
            items=self.case();c,p,a,permit,v,adapter,state=items
            if change=='primary':c.primary=False
            elif change=='uuid':c.uuids['transactions']=Binary(b'x'*16,4)
            elif change=='journal_uuid':c.uuids[JOURNAL]=Binary(b'x'*16,4)
            elif change=='r6':c.docs['moneyflow_metadata'][0]['environment_id']='other'
            elif change=='marker':c.docs['moneyflow_metadata'][1]['nonce']='other'
            elif change=='destination':c.address=('remote',27018)
            else:c.replica='other'
            self.assertEqual(self.execute(*items)['state'],'blocked')
            self.assertFalse([x for x in c.calls if x[0] in ('insert','update')])
    def test_registry_existing_other_owner_blocks(self):
        items=self.case();c,p,a,permit,v,adapter,state=items
        c.docs[JOURNAL].append({**adapter._record(),'owner':'other'})
        self.assertEqual(self.execute(*items)['state'],'blocked');self.assertFalse(c.sessions)
    def test_current_not_old_plan(self):
        items=self.case();c,p,a,*rest=items;c.docs['transactions'][0]['amount']='99'
        self.assertEqual(self.execute(*items)['state'],'blocked')
        self.assertNotIn('_history_keys',c.docs['transactions'][0])
    def test_administrative_change_preserved(self):
        items=self.case();c=items[0];c.docs['transactions'][0]['notes']='keep'
        self.assertEqual(self.execute(*items)['state'],'confirmed');self.assertEqual(c.docs['transactions'][0]['notes'],'keep')
    def test_null_and_existing_block_rejected(self):
        for value in (None,{}):
            items=self.case();items[0].docs['transactions'][0]['_history_keys']=value
            self.assertEqual(self.execute(*items)['state'],'blocked')
            self.assertFalse([x for x in items[0].calls if x[0]=='update'])
    def test_bson_numeric_sources(self):
        for value in (Int64(70),70.0,'70'):
            items=self.case([row(1,amount=70)]);items[0].docs['transactions'][0]['amount']=value
            self.assertEqual(self.execute(*items)['state'],'blocked')
    def test_numeric_physical_id(self):
        items=self.case();items[0].docs['transactions'][0]['_id']=Int64(1)
        self.assertEqual(self.execute(*items)['state'],'blocked')
    def test_filter_literal_types_and_absence(self):
        current=row(1,amount=Int64(70),date='$date');query=cas_filter(current)
        self.assertEqual(query['_history_keys'],{'$exists':False})
        parts=query['$expr']['$and']
        self.assertIn({'$eq':[{'$type':'$amount'},'long']},parts)
        self.assertIn({'$eq':['$date',{'$literal':'$date'}]},parts)
        del current['amount'];parts=cas_filter(current)['$expr']['$and']
        self.assertIn({'$eq':[{'$type':'$amount'},'missing']},parts)
        current['amount']=None
        self.assertIn({'$eq':[{'$type':'$amount'},'null']},cas_filter(current)['$expr']['$and'])
    def test_cas_zero_rollback(self):
        items=self.case();c=items[0];c.cas_zero=True
        self.assertEqual(self.execute(*items)['state'],'blocked');self.assertNotIn('_history_keys',c.docs['transactions'][0])
        self.assertEqual(len(c.docs[JOURNAL]),1)
    def test_receipt_insert_failure_rolls_back_update(self):
        items=self.case();c=items[0];c.insert_error=OperationFailure('SECRET')
        self.assertEqual(self.execute(*items)['state'],'blocked');self.assertNotIn('_history_keys',c.docs['transactions'][0])
        self.assertEqual(c.sessions[0].aborts,1);self.assertEqual(len(c.docs[JOURNAL]),1)
    def test_transient_whole_transaction_retry(self):
        items=self.case();c=items[0]
        c.commit_errors=[OperationFailure('SECRET',details={'errorLabels':['TransientTransactionError']})]
        self.assertEqual(self.execute(*items)['state'],'confirmed');self.assertEqual(len(c.sessions),2)
        self.assertEqual(len(c.docs[JOURNAL]),2)
    def test_unknown_commit_retry_original_session(self):
        items=self.case();c=items[0];c.commit_errors=['after']
        self.assertEqual(self.execute(*items)['state'],'confirmed');self.assertEqual(len(c.sessions),1)
        self.assertEqual(c.sessions[0].commits,2);self.assertEqual(c.sessions[0].aborts,0)
    def test_unknown_priority_and_persistent_absent_evidence(self):
        items=self.case();c,p,a,permit,v,adapter,state=items
        c.commit_errors=[OperationFailure('SECRET',details={'errorLabels':['UnknownTransactionCommitResult','TransientTransactionError']})]*3
        r=self.execute(*items);self.assertEqual(r['state'],'uncertain');self.assertEqual(len(c.sessions),1)
        self.assertEqual(c.sessions[0].aborts,0);self.assertIsNotNone(state.pending)
        fresh=SyntheticMongoApplyAdapter(c,p,replace(permit,operation='reconcile'),v)
        r=reconcile(fresh,p,a.target,a,state)
        self.assertEqual(r['state'],'uncertain');self.assertIsNotNone(state.pending)
    def test_reconciliation_matching_and_no_writes(self):
        items=self.case();c,p,a,permit,v,adapter,state=items;c.commit_errors=['after']
        r=apply_plan(adapter,p,a.target,a,state,budgets=replace(Budgets(),commit_attempts=1))
        self.assertEqual(r['state'],'uncertain')
        before=deepcopy(c.docs);c.calls=[]
        fresh=SyntheticMongoApplyAdapter(c,p,replace(permit,operation='reconcile'),v)
        self.assertEqual(reconcile(fresh,p,a.target,a,state)['state'],'original_confirmed')
        self.assertEqual(c.docs,before);self.assertFalse([x for x in c.calls if x[0] in ('insert','update')])
        with self.assertRaises(Conflict):fresh.begin(time.monotonic()+1)
    def test_existing_receipt_strict_comparison(self):
        for corrupt in (False,True):
            items=self.case();c,p,a,permit,v,adapter,state=items
            e=evidence_for(p,p.intents[0],a)
            receipt={'_id':'receipt:'+e.key,**asdict(e)}
            if corrupt:receipt['source_sha256']='other'
            c.docs[JOURNAL].append(receipt)
            r=self.execute(*items)
            self.assertEqual(r['state'],'blocked' if corrupt else 'confirmed')
            self.assertFalse([x for x in c.calls if x[0]=='update'])
    def test_restart_apply_denied_even_new_controller(self):
        items=self.case();c,p,a,permit,v,adapter,state=items;self.execute(*items)
        fresh=SyntheticMongoApplyAdapter(c,p,permit,v)
        self.assertEqual(apply_plan(fresh,p,a.target,a,RunState())['state'],'blocked')
    def test_namespace_and_operations_audit(self):
        items=self.case();c=items[0];self.execute(*items)
        for op,name,value,session in c.calls:
            self.assertIn(op,('hello','buildInfo','listCollections','find','insert','update'))
            if op=='insert':self.assertEqual(name,JOURNAL)
            if op=='update':self.assertEqual(name,'transactions');self.assertEqual(set(value[1]['$set']),{'_history_keys'})
        self.assertTrue(c.info_closed)
    def test_network_read_and_cleanup_privacy(self):
        items=self.case();c=items[0];c.read_error=ConnectionFailure('SECRET')
        r=self.execute(*items);self.assertEqual(r['state'],'blocked');self.assertNotIn('SECRET',json.dumps(r))
        items=self.case();c=items[0];c.cleanup_error=True
        self.assertIn('blocked',self.execute(*items)['state'])
    def test_adapter_deadline_and_document_budget(self):
        items=self.case();adapter=items[-2];adapter.deadline=time.monotonic()-1
        self.assertEqual(self.execute(*items)['state'],'blocked')
        items=self.case();items[0].docs['transactions'][0]['notes']='x'*1048576
        self.assertEqual(self.execute(*items)['state'],'blocked')
    def test_report_privacy(self):
        r=self.execute(*self.case());encoded=json.dumps(r)
        for token in ('mongodb://','synthetic-1','70.123','2026-W40','physical_id','source_sha256'):
            self.assertNotIn(token,encoded)
        self.assertFalse(r['indexed_reads_allowed']);self.assertFalse(r['operational_apply_authorized'])
    def test_unacknowledged_registry_cannot_begin_transaction(self):
        items=self.case();c=items[0];c.unacknowledged=True
        self.assertEqual(self.execute(*items)['state'],'blocked');self.assertFalse(c.sessions)
    def test_wrong_authorization_and_uuid_before_writes(self):
        c,p,a,permit,v,adapter,state=self.case()
        with self.assertRaises(Conflict):
            SyntheticMongoApplyAdapter(c,p,replace(permit,authorization=replace(a,plan_digest='other')),v)
        with self.assertRaises(Conflict):SyntheticMongoApplyAdapter(c,p,replace(permit,journal_uuid=None),v)
        self.assertFalse(c.calls)
    def test_ddl_and_exclusion_loss_before_stage(self):
        items=self.case();c,p,a,permit,v,adapter,state=items
        original=c['transactions'].find_one
        # Observations are rechecked before every mutation, not trusted once.
        class ChangingVerifier(Verifier):
            def verify(self,permit,deadline):
                self.calls+=1
                if self.calls>=5:return replace(self.value,ddl_excluded=False)
                return self.value
        adapter.verifier=ChangingVerifier(a.target)
        self.assertEqual(self.execute(*items)['state'],'blocked')
        self.assertNotIn('_history_keys',c.docs['transactions'][0])
    def test_no_raw_source_or_update_substitution(self):
        c,p,a,permit,v,adapter,state=self.case()
        binding=(p.run_id,p.digest,a.target.binding(),a.revision,a.exclusion_epoch)
        adapter.bind_controller(state,binding);state.binding=binding
        tx=adapter.begin(time.monotonic()+5)
        doc=tx.read(p.intents[0].physical_id);e=evidence_for(p,p.intents[0],a)
        with self.assertRaises(Conflict):tx.stage(BSON.encode({**doc,'amount':'99'}),p.intents[0].proposed_keys,e)
        with self.assertRaises(Conflict):tx.stage(BSON.encode(doc),BSON.encode({'value':{'$set':{'balance':99}}}),e)
        self.assertFalse([x for x in c.calls if x[0]=='update'])
        tx.close(time.monotonic()+2);adapter.close(time.monotonic()+2)

    def test_unowned_transaction_or_session_cannot_write(self):
        from backend.history_apply_mongodb import SyntheticTransaction
        c,p,a,permit,v,adapter,state=self.case()
        session=Session(c);tx=SyntheticTransaction(adapter,session,time.monotonic()+5)
        with self.assertRaises(Conflict):tx.read(p.intents[0].physical_id)
        with self.assertRaises(Conflict):tx.commit()
        with self.assertRaises(Conflict):adapter.receipt(next(iter(adapter.allowed)),session=session)
        self.assertFalse(c.calls)
    def test_network_commit_is_uncertain_not_rollback(self):
        items=self.case();c,p,a,permit,v,adapter,state=items
        c.commit_errors=[ConnectionFailure('SECRET')]*3
        self.assertEqual(self.execute(*items)['state'],'uncertain')
        self.assertIsNotNone(state.pending);self.assertEqual(len(c.sessions),1)
        self.assertEqual(c.sessions[0].aborts,0)
    def test_transient_stage_retry_revalidates(self):
        items=self.case();c=items[0]
        original=c.update_error
        class OnceCollection(Collection):
            def update_one(self,*args,**kwargs):
                if self.client.update_error:
                    error=self.client.update_error;self.client.update_error=None;raise error
                return super().update_one(*args,**kwargs)
        c.update_error=OperationFailure('SECRET',details={'errorLabels':['TransientTransactionError']})
        items[-2].movements=OnceCollection(c,'transactions')
        self.assertEqual(self.execute(*items)['state'],'confirmed');self.assertEqual(len(c.sessions),2)

    def test_uuid_change_after_unknown_stops_commit_retry(self):
        items=self.case();c,p,a,permit,v,adapter,state=items
        original_start=c.start_session
        def start(**kwargs):
            session=original_start(**kwargs);original_commit=session.commit_transaction
            def commit():
                try:return original_commit()
                finally:c.uuids['transactions']=Binary(b'x'*16,4)
            session.commit_transaction=commit;return session
        c.start_session=start;c.commit_errors=['after']
        self.assertEqual(self.execute(*items)['state'],'uncertain')
        self.assertEqual(c.sessions[0].commits,1);self.assertIsNotNone(state.pending)

    def test_import_without_effects(self):
        script="""
from unittest.mock import patch
import sys
with patch('pymongo.MongoClient',side_effect=AssertionError('connected')),patch('builtins.open',side_effect=AssertionError('file')):
 import backend.history_apply_mongodb
assert not any(n.startswith('backend.experiments') for n in sys.modules)
"""
        r=subprocess.run([sys.executable,'-B','-c',script],capture_output=True,text=True)
        self.assertEqual(r.returncode,0,r.stderr)


if __name__=='__main__':unittest.main()
