import unittest
import tempfile
import json
from pathlib import Path
from compare_firmware_io import sha
from host_clock_widths import widths, clock_samples, board_clock_capture

TIMING={'highWidthMinimumSeconds':180e-9,'lowWidthMinimumSeconds':180e-9,'periodMinimumSeconds':400e-9}

class WidthTests(unittest.TestCase):
    def test_long_pulses_pass_without_qualifying_censored_ends(self):
        samples=[(i*1e-9,3 if 300<=i<600 or 900<=i<1200 else 0,0)for i in range(1500)]
        r=widths(samples,TIMING)
        self.assertTrue(r['screenPassed']);self.assertFalse(r['qualified'])
        self.assertEqual([x['side']for x in r['censoredIntervals']],['left','right'])

    def test_short_and_uncertain_pulses_are_not_passes(self):
        for width,status in ((100,'fail'),(180,'indeterminate')):
            samples=[(i*1e-9,3 if 200<=i<200+width else 0,0)for i in range(500)]
            r=widths(samples,TIMING)
            high=next(x for x in r['measurements']if x['kind']=='high')
            self.assertEqual(high['status'],status);self.assertFalse(r['screenPassed'])

    def test_missing_activity_and_bad_samples(self):
        self.assertFalse(widths([(0,0,0),(1,0,0)],TIMING)['screenPassed'])
        for samples in ([],[(0,0,0)],[(0,0,0),(0,3,0)],[(0,0,0),(1,float('nan'),0)]):
            with self.assertRaises(ValueError):widths(samples,TIMING)

class BoardClockTests(unittest.TestCase):
    def test_startup_review_requires_zero_sample(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'trace.txt'
            header='time v(cpu_clock) v(cpu_reset) v(receiver_data) v(receiver_clock)\n'
            for first in (0,1e-10):
                p.write_text(header+f'{first} 0 0 0 0\n1e-9 0 0 0 0\n2e-9 0 0 0 0\n')
                if first == 0:
                    self.assertEqual(len(list(clock_samples(p,1,2e-9,start=0,board=True))),3)
                else:
                    with self.assertRaises(ValueError):list(clock_samples(p,1,2e-9,start=0,board=True))

    def test_window_and_hash_checks_preserve_failed_producer(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/'boot.cir').write_text('fixture\n.control\ntran 1n 0.124000002 124m\n.endc\n.end\n')
            (p/'ngspice.log').write_text('Completed capture\n')
            (p/'host-trace.txt').write_text('Retained host capture\n')
            header='time v(cpu_clock) v(cpu_reset) v(receiver_data) v(receiver_clock)\n'
            good=header+'0.12400000025 0 5 3 0\n0.124000001 0 5 3 3\n0.124000002 0 5 3 0\n'
            (p/'trace.txt').write_text(good)
            report={'passed':False,'qualified':False,'error':'Firmware mismatch',
                    'assumptions':{'hostBuffer':'7404-candidate','maximumStepNs':1,
                                   'traceWindowSeconds':[.124,.124000002]}}
            for name,key in [('boot.cir','deckSha256'),('ngspice.log','logSha256'),
                             ('host-trace.txt','hostTraceSha256'),('trace.txt','traceSha256')]:
                report[key]=sha(p/name)
            (p/'report.json').write_text(json.dumps(report))
            original,start,end,step=board_clock_capture(p)
            self.assertFalse(original['passed'])
            self.assertEqual(original['error'],'Firmware mismatch')
            samples=list(clock_samples(p/'trace.txt',step,end,start=start,board=True))
            self.assertEqual(len(samples),3)
            self.assertFalse(widths(samples,TIMING)['screenPassed'])
            for invalid in (good.replace('v(receiver_clock)','v(wrong)'),
                            good.replace('0.12400000025','0.1240000015'),
                            '\n'.join(good.splitlines()[:-1])+'\n'):
                (p/'trace.txt').write_text(invalid)
                with self.assertRaises(ValueError):
                    list(clock_samples(p/'trace.txt',step,end,start=start,board=True))
                with self.assertRaises(ValueError):board_clock_capture(p)
            (p/'trace.txt').write_text(good)
            report['preparedOnly']=True
            (p/'report.json').write_text(json.dumps(report))
            with self.assertRaises(ValueError):board_clock_capture(p)

if __name__=='__main__':unittest.main()
