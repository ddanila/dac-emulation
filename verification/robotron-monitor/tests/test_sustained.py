import copy
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import sustained
import solver_profile
from test_frames import capture


class SustainedTests(unittest.TestCase):
    def test_original_static_fields_and_preroll_required(self):
        d=capture(lines=16000)
        report=sustained.select(d)
        self.assertEqual(report['status'],'complete')
        self.assertEqual(len(report['selection']['frame_ticks']),16)
        self.assertTrue(report['source_content_verified'])
        self.assertFalse(report['monitor_lock_verified'])
        self.assertFalse(report['input_repeated'])
        self.assertEqual(sustained.select(capture())['status'],'incomplete')
        self.assertEqual(sustained.select(d,tau_s=1)['status'],'incomplete')
        changing=copy.deepcopy(d)
        for e in changing['events']:e[3]=(e[0]//3600000)%2
        self.assertEqual(sustained.select(changing)['status'],'incomplete')
        missing=capture(lines=11000,missing=(4200,))
        self.assertEqual(sustained.select(missing)['status'],'incomplete')

    def records(self):
        return [dict(start_s=i*.02,end_s=(i+1)*.02,locked=True,phase_error_lines=0.,
                     source_content_sha256='a'*64,metrics=dict(p41_v=41,p22_v=22,n16_magnitude_v=16,
                         eht_v=11000,width_m=.2,height_m=.14,brightness_w_m2=1)) for i in range(24)]

    def test_stability_rejects_drift_lock_loss_darkness_and_empty_phosphor(self):
        records=self.records()
        self.assertTrue(sustained.assess(records,phosphor_preroll_s=.2)['accepted'])
        self.assertFalse(sustained.assess(records,phosphor_preroll_s=.01)['accepted'])
        self.assertFalse(sustained.assess(records[:-1],phosphor_preroll_s=.2)['accepted'])
        for key,value in [('locked',False),('phase_error_lines',.02),('source_content_sha256','b'*64),('start_s',.459)]:
            changed=copy.deepcopy(records);changed[-1][key]=value
            self.assertFalse(sustained.assess(changed,phosphor_preroll_s=.2)['accepted'])
        for metric in records[0]['metrics']:
            changed=copy.deepcopy(records);changed[-1]['metrics'][metric]*=1.03
            self.assertFalse(sustained.assess(changed,phosphor_preroll_s=.2)['accepted'])
        for bad in (0,float('nan')):
            changed=copy.deepcopy(records);changed[-1]['metrics']['brightness_w_m2']=bad
            with self.assertRaises(ValueError):sustained.assess(changed,phosphor_preroll_s=.2)


class ProfileTests(unittest.TestCase):
    def test_complete_truncated_and_nonmonotonic_raw(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'trace.raw'
            header=b'Title: test\nFlags: real\nNo. Variables: 2\nNo. Points: 3\nVariables:\n0 time time\n1 v(x) voltage\nBinary:\n'
            data=b''.join(struct.pack('=2d',t,v) for t,v in [(0,0),(.001,2),(.001000000001,3)])
            path.write_bytes(header+data)
            report=solver_profile.profile(path,expected_end_s=.001000000001)
            self.assertTrue(report['completed_endpoint']);self.assertIsNone(report['rejected_steps'])
            self.assertEqual(report['millisecond_bins'][1]['subnanosecond_steps'],1)
            path.write_bytes(header+data[:-1])
            self.assertFalse(solver_profile.profile(path,expected_end_s=.001000000001)['completed_endpoint'])
            path.write_bytes(header.replace(b'Points: 3',b'Points: 0')+data)
            self.assertFalse(solver_profile.profile(path,expected_end_s=.001000000001)['completed_endpoint'])
            path.write_bytes(header+data+struct.pack('=2d',0,2))
            with self.assertRaises(ValueError):solver_profile.profile(path,expected_end_s=.001)


if __name__=='__main__':unittest.main()
