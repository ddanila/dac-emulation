import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from private_sync_family_board_review import family,inventory,snapshot,verify_symbols
IDENTITIES={'ivlng.vpi':{'path':'/fixture/ivlng.vpi','sha256':'bridge','symbols':{'next_advance_cb':16}},
            'system.vpi':{'path':'/fixture/system.vpi','sha256':'display','symbols':{'strobe_cb':32}}}


def shot(sync=1):
    return ['VF_BEGIN 1 5000000 4 2',
            'VF_CB 1 1 0 9 1 1 1 1 1 1 1 1 1 2 0 5000000 0x0p+0',
            'VF_CODE 1 '+b'/fixture/ivlng.vpi'.hex()+' 10',
            f'VF_CB 2 0 {sync} 7 1 1 0 -1 -1 -1 1 1 1 2 0 0 0x0p+0',
            'VF_CODE 2 '+b'/fixture/system.vpi'.hex()+' 20','VF_END']


def boundary(index,negative=False):
    lines=[f'VF_BRIDGE {index} '+('after-step' if index%2 else 'before-step')+' 0.000005','VF_STAGE before',*shot()]
    if negative:return lines+['VF_STAGE changed',*shot(0),'VF_STAGE restored',*shot(),'VF_FAULT detected=1 restored=1']
    return lines+['VF_STAGE repeat',*shot(),'VF_STABLE equal=1']


class FamilyBoardTests(unittest.TestCase):
    def review(self,lines,negative=False):
        with patch('private_sync_family_board_review.records',return_value=iter(lines)):
            return inventory(None,IDENTITIES,corrupt=negative)

    def test_identified_display_does_not_imply_payload_coverage(self):
        r=self.review(boundary(0)+boundary(1))
        self.assertTrue(r['functionIdentityEstablished'])
        self.assertFalse(r['payloadCoverageComplete'])
        self.assertFalse(r['displayReferentsObserved'])
        self.assertEqual(r['functionObservations']['strobe_cb'],2)
        self.assertIsNotNone(self.review(boundary(0,True),True)['fault'])

    def test_unknown_functions_bad_boundaries_and_unrestored_fault_rejected(self):
        positive=boundary(0)+boundary(1)
        cases=[positive[:-1],positive[1:],
               [s.replace('VF_BRIDGE 1','VF_BRIDGE 2') for s in positive],
               [s.replace('VF_STABLE equal=1','VF_STABLE equal=0') for s in positive],
               [s[:-2]+'21' if s.startswith('VF_CODE 2 ') else s for s in positive]]
        for lines in cases:
            with self.assertRaises(ValueError):self.review(lines)
        bad=boundary(0,True);i=bad.index('VF_STAGE restored')+4;bad[i]=bad[i].replace('VF_CB 2 0 1','VF_CB 2 0 0')
        with self.assertRaises(ValueError):self.review(bad,True)

    def test_module_hash_and_symbol_table_must_match_capture(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'symbols.json').write_text(json.dumps(IDENTITIES))
            (root/'ivlng.vpi.nm').write_text('00000010 t _next_advance_cb\n')
            (root/'system.vpi.nm').write_text('00000020 t _strobe_cb\n')
            runs={'off':{'externalDependencies':[{'path':e['path'],'sha256':e['sha256']} for e in IDENTITIES.values()]}}
            self.assertEqual(verify_symbols(root,runs),IDENTITIES)
            runs['off']['externalDependencies'][0]['sha256']='changed'
            with self.assertRaises(ValueError):verify_symbols(root,runs)
            runs['off']['externalDependencies'][0]['sha256']='bridge'
            (root/'system.vpi.nm').write_text('00000021 t _strobe_cb\n')
            with self.assertRaises(ValueError):verify_symbols(root,runs)


if __name__=='__main__':unittest.main()
