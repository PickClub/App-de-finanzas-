"""Offline policy oracle. No client, persistent HMAC, snapshot or backup adapter.

Infrastructure/crypto evidence is injected by fixtures, never verified by this file.
"""
from copy import deepcopy
import unittest

from bson import BSON
from bson.binary import Binary
from bson.int64 import Int64
from bson.objectid import ObjectId
from bson.timestamp import Timestamp
from bson.decimal128 import Decimal128

from backend.history_keys import derive_history_keys, inspect_history_keys
from backend.experiments.c3_history_diagnosis_offline import physical_key


class Abort(ValueError):
    pass


BINDING = {'run_id': 'synthetic-consistency-run', 'environment': 'synthetic-context',
           'database': 'synthetic-only', 'collection_uuid': Binary(b'x'*16, 4),
           'scope': 'entire_effective_user', 'user_id': 'default-user',
           'key_version': 1, 'generation': 1, 'type_policy': 'supported-subset-v1',
           'revision': '4585e5293b7466f3a58c7faf783bd8707253d8ac'}


def checkpoint_policy(token, expected, *, now, mac_valid=True, latest=True,
                      snapshot_retained=True, copy_immutable=True, key_allowed=True):
    # Design semantics only: no HMAC computation or persistence implemented.
    if not mac_valid or not latest or not key_allowed:
        raise Abort('checkpoint_authenticity_or_progress')
    if token['binding'] != expected or now >= token['expires_at']:
        raise Abort('checkpoint_binding_or_expiry')
    if token['mode'] == 'snapshot' and (type(token['anchor']) is not Timestamp or not snapshot_retained):
        raise Abort('snapshot_unavailable')
    if token['mode'] == 'copy' and (not copy_immutable or not token['anchor']):
        raise Abort('copy_unverifiable')
    if token['mode'] not in ('live', 'snapshot', 'copy'):
        raise Abort('unsupported_mode')
    return deepcopy(token)


def assess(rows, *, mode, completed=True, expected_total=None, stable=True,
           evidence_valid=True, resource_ok=True, duplicate_pass=True, expired=False):
    if mode not in ('live','snapshot','copy'):
        raise Abort('unsupported_mode')
    result = {'state': 'incompleto', 'counts': {}, 'visited': 0, 'duplicate_groups': 0,
              'certificate_issued': False, 'indexed_reads_allowed': False, 'evidence': 'offline_policy'}
    if not evidence_valid or not resource_ok or expired or (mode != 'live' and not stable):
        return {**result, 'state': 'abortado'}
    seen, duplicate_groups = set(), set()  # Small-fixture oracle, not scalable detection.
    for row in rows:
        try:
            physical_key(row['_id'])
            if (row.get('user_id') != 'default-user' or type(row.get('id')) is not str
                    or not 1 <= len(row['id']) <= 256):
                raise ValueError()
        except (KeyError, ValueError):
            return {**result, 'state': 'abortado'}
        state = inspect_history_keys(row, 1)
        result['counts'][state] = result['counts'].get(state,0)+1
        result['visited'] += 1
        identity = (row.get('user_id'), row.get('id'))
        if identity in seen: duplicate_groups.add(identity)
        seen.add(identity)
    result['duplicate_groups'] = len(duplicate_groups)
    if mode == 'live':
        result['state'] = 'exploratorio'
    elif not completed or not duplicate_pass:
        result['state'] = 'incompleto'
    elif expected_total != result['visited']:
        result['state'] = 'abortado'
    else:
        result['state'] = 'consistente'
        if set(result['counts']) <= {'ready'} and not duplicate_groups:
            result['state'] = 'certificable'
    return result


def row(i, **fields):
    r = {'_id': i, 'id': f'synthetic-{i}', 'user_id': 'default-user',
         'date': '2026-W40-4T12:00:00.123456+01:02:03', 'amount': Decimal128('70.1200'), **fields}
    r['_history_keys'] = derive_history_keys(r,1)
    return r


class ConsistencyPolicyTests(unittest.TestCase):
    def setUp(self):
        self.rows = [row(2),row(4)]
        self.snapshot_bytes = tuple(BSON.encode(r) for r in self.rows)
        self.token = {'binding': deepcopy(BINDING), 'mode': 'snapshot', 'anchor': Timestamp(100,1),
                      'expires_at': 400, 'sequence': 1, 'key_id': 'synthetic-key-epoch'}

    def stable_rows(self):return [BSON(b).decode() for b in self.snapshot_bytes]

    def test_insert_before_checkpoint_omitted_in_live(self):
        live = [row(1)] + self.rows
        tail = [r for r in live if physical_key(r['_id']) > physical_key(2)]
        self.assertEqual(len(tail),1)
        result=assess([self.rows[0]]+tail,mode='live',expected_total=3)
        self.assertEqual(result['state'],'exploratorio')

    def test_post_anchor_insert_not_part_of_snapshot(self):
        live=self.rows+[row(6)]
        self.assertEqual(len(live),3)
        result=assess(self.stable_rows(),mode='snapshot',expected_total=2)
        self.assertEqual(result['state'],'certificable')
        self.assertFalse(result['indexed_reads_allowed'])

    def test_post_checkpoint_edit_does_not_change_fixture_snapshot(self):
        changed=deepcopy(self.rows);changed[0]['amount']=Decimal128('99')
        self.assertEqual(assess(changed,mode='live')['counts']['stale_or_corrupt'],1)
        self.assertEqual(assess(self.stable_rows(),mode='snapshot',expected_total=2)['counts'],{'ready':2})

    def test_delete_does_not_remove_snapshot_fixture_row(self):
        live=self.rows[1:]
        self.assertEqual(len(live),1)
        self.assertEqual(len(self.stable_rows()),2)

    def test_process_resume_same_anchor_and_binding(self):
        recovered=checkpoint_policy(self.token,BINDING,now=200)
        self.assertEqual(recovered['anchor'],Timestamp(100,1))
        self.assertEqual(assess(self.stable_rows(),mode='snapshot',expected_total=2)['state'],'certificable')

    def test_snapshot_expired_at_server_aborts(self):
        with self.assertRaisesRegex(Abort,'snapshot_unavailable'):
            checkpoint_policy(self.token,BINDING,now=200,snapshot_retained=False)
        self.assertEqual(assess(self.rows,mode='snapshot',expected_total=2,expired=True)['state'],'abortado')

    def test_checkpoint_expiry_no_fallback(self):
        with self.assertRaises(Abort):checkpoint_policy(self.token,BINDING,now=400)

    def test_manipulated_hmac_rejected(self):
        with self.assertRaises(Abort):checkpoint_policy(self.token,BINDING,now=200,mac_valid=False)

    def test_old_sequence_rejected(self):
        with self.assertRaises(Abort):checkpoint_policy(self.token,BINDING,now=200,latest=False)

    def test_rotation_must_explicitly_allow_key(self):
        with self.assertRaises(Abort):checkpoint_policy(self.token,BINDING,now=200,key_allowed=False)
        self.assertEqual(checkpoint_policy(self.token,BINDING,now=200,key_allowed=True)['key_id'],'synthetic-key-epoch')

    def test_context_generation_uuid_types_and_revision_bound(self):
        for field,value in [('environment','other'),('generation',2),('database','other'),
                            ('collection_uuid',Binary(b'y'*16,4)),('type_policy','other'),('revision','other')]:
            with self.subTest(field=field):
                expected={**BINDING,field:value}
                with self.assertRaises(Abort):checkpoint_policy(self.token,expected,now=200)

    def test_stable_copy_requires_immutable_verified_anchor(self):
        token={**self.token,'mode':'copy','anchor':'synthetic-backup-manifest-digest'}
        checkpoint_policy(token,BINDING,now=200)
        with self.assertRaises(Abort):checkpoint_policy(token,BINDING,now=200,copy_immutable=False)
        self.assertEqual(assess(self.rows,mode='copy',expected_total=2)['state'],'certificable')

    def test_changed_stable_view_aborts(self):
        self.assertEqual(assess(self.rows,mode='copy',expected_total=2,stable=False)['state'],'abortado')

    def test_partial_scan_not_consistent(self):
        self.assertEqual(assess(self.rows[:1],mode='snapshot',completed=False,expected_total=2)['state'],'incompleto')

    def test_total_mismatch_aborts(self):
        self.assertEqual(assess(self.rows,mode='snapshot',expected_total=3)['state'],'abortado')

    def test_duplicate_pass_missing_not_certificable(self):
        self.assertEqual(assess(self.rows,mode='snapshot',expected_total=2,duplicate_pass=False)['state'],'incompleto')

    def test_duplicates_consistent_but_not_certificable(self):
        rows=[row(1,id='same'),row(2,id='same')]
        r=assess(rows,mode='snapshot',expected_total=2)
        self.assertEqual(r['state'],'consistente');self.assertEqual(r['duplicate_groups'],1)

    def test_each_key_defect_consistent_but_not_healthy(self):
        variants=[]
        missing=row(1);missing.pop('_history_keys');variants.append(missing)
        stale=row(1);stale['amount']=Decimal128('71');variants.append(stale)
        variants.append(row(1,date='invalid-synthetic'))
        incompatible=row(1);incompatible['_history_keys']['generation']=2;variants.append(incompatible)
        for doc in variants:
            self.assertEqual(assess([doc],mode='snapshot',expected_total=1)['state'],'consistente')

    def test_mixed_bson_ids_supported_in_snapshot_fixture(self):
        values=[1,Int64(2),'synthetic',Binary(b'x',0),ObjectId()]
        rows=[row(v,id=f'synthetic-{i}') for i,v in enumerate(values)]
        self.assertEqual(assess(rows,mode='snapshot',expected_total=5)['state'],'certificable')

    def test_resource_limits_abort_not_partial_success(self):
        self.assertEqual(assess(self.rows,mode='snapshot',resource_ok=False)['state'],'abortado')

    def test_majority_or_hmac_does_not_certify_live(self):
        self.assertEqual(assess(self.rows,mode='live',stable=True,evidence_valid=True)['state'],'exploratorio')

    def test_wrong_user_or_identity_aborts(self):
        for doc in (row(1,user_id='other'),row(1,id=None)):
            self.assertEqual(assess([doc],mode='snapshot',expected_total=1)['state'],'abortado')

    def test_unsupported_physical_type_aborts(self):
        self.assertEqual(assess([row(True)],mode='snapshot',expected_total=1)['state'],'abortado')

    def test_report_contains_no_values_or_snapshot_documents(self):
        report=assess(self.rows,mode='snapshot',expected_total=2)
        for value in ('70.1200','2026-W','synthetic-2'):
            self.assertNotIn(value,str(report))
        self.assertFalse(report['certificate_issued'])


if __name__=='__main__':unittest.main()
