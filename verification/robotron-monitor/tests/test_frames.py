import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import frames,full_path


def capture(*,lines=1300,vertical=True,missing=()):
    events=[[0,0,1,1]]
    for line in range(lines):
        if line in missing:continue
        t=100+line*9000
        width=7940 if vertical and line%400 in (40,41,42) else 1060
        events.extend([[t,line%2,0,1],[t+width,line%2,1,1]])
    events.append([lines*9000+99,0,1,1])
    return dict(format='dac-monitor-input-v2',clock_hz=179712000,
        signals=['VIDEO','BSYN','INTENS'],board_revision='1.93.310412.6/04',
        qualification='synthetic-test-pattern',time_origin={'dot_tick':0},assumptions=[],events=events)


class FrameTests(unittest.TestCase):
    def test_complete_fields_integer_timing_and_original_events_preserved(self):
        d=capture();original=copy.deepcopy(d)
        r=frames.analyze(d)
        self.assertEqual(r['status'],'complete')
        self.assertEqual(r['line_period_ticks'],9000)
        self.assertEqual(r['selection'],dict(simulate_from_tick=0,render_start_tick=3960100,
            render_end_tick=7560100,frame_ticks=[7560100]))
        self.assertFalse(r['input_repeated']);self.assertFalse(r['monitor_lock_verified'])
        self.assertEqual(d,original)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'capture.json';raw=json.dumps(d).encode();path.write_bytes(raw)
            out=Path(tmp)/'prepared';r=frames.prepare(path,out)
            self.assertEqual((out/'input.json').read_bytes(),raw)
            self.assertEqual(json.loads((out/'fields.json').read_text()),r)

    def test_no_vertical_sync_or_stopped_raster_not_fabricated(self):
        for d in (capture(vertical=False),dict(capture(),events=[[0,0,1,1],[1000000,0,1,1]])):
            r=frames.analyze(d);self.assertEqual(r['status'],'incomplete');self.assertIsNone(r['selection'])

    def test_truncated_capture_and_missing_line_refuse_selection(self):
        for d in (capture(lines=800),capture(missing=(500,)),capture(missing=range(500,510)),capture(missing=range(840,843))):
            self.assertEqual(frames.analyze(d)['status'],'incomplete')
        d=capture();d['events']=d['events'][:1684]
        self.assertEqual(frames.analyze(d)['status'],'incomplete')

    def test_v1_and_invalid_requests_rejected(self):
        with self.assertRaises(ValueError):frames.analyze(dict(capture(),format='dac-monitor-input-v1'))
        for n in (0,17,True):
            with self.assertRaises(ValueError):frames.analyze(capture(),fields=n)

    def test_partial_initial_sync_does_not_create_boundary(self):
        d=capture();start=41*9000+500
        state=next(e for e in reversed(d['events']) if e[0]<=start)
        d['events']=[[0,*state[1:]]]+[[e[0]-start,*e[1:]] for e in d['events'] if e[0]>start]
        r=frames.analyze(d,pre_roll_fields=0)
        self.assertEqual(r['status'],'complete')
        self.assertEqual(r['field_boundaries'][0],440*9000+100-start)

    def test_preflight_never_promotes_audit_or_synthetic_trace_to_render(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'capture.json';p.write_text(json.dumps(capture()))
            def fake_audit(out):
                out.mkdir();(out/'audit.json').write_text('{}')
                return dict(blockers=[],full_path_render_eligible=True)
            with patch.object(full_path.full_path_audit,'audit',fake_audit):
                r=full_path.run(p,root/'run')
            self.assertEqual(r['status'],'blocked')
            self.assertFalse(r['numerical_acceptance']);self.assertFalse(r['assembly_complete'])
            self.assertIn('connected-solver',[b['id'] for b in r['blockers']])
            self.assertFalse(list((root/'run').rglob('*.png')))
            with self.assertRaises(ValueError):full_path.run(p,root/'bad',candidate='invented')
            self.assertFalse((root/'bad').exists())

if __name__=='__main__':unittest.main()
