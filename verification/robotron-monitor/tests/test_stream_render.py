import csv
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import beam_render
import stream_render
import image_acceptance
from test_beam_render import row


class StreamExportTests(unittest.TestCase):
    def test_streamed_replay_matches_in_memory_renderer(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trace=root/'trace.csv'
            rows=[row(0),row(2e-7),row(4e-7,beam=0)]
            with trace.open('w') as stream:
                writer=csv.writer(stream);writer.writerow(beam_render.FIELDS);writer.writerows(rows)
            surface=dict(width=32,height=24)
            report=stream_render.run(trace,root/'stream',[0,2e-7,4e-7],surface=surface)
            self.assertEqual(report['status'],'complete');self.assertEqual(report['electrical_rows'],3)
            self.assertFalse(report['full_monitor_qualified'])
            self.assertEqual(report['surface_parameters']['width'],32)
            self.assertEqual(len(report['linear_frames']),3)
            for index,frame in enumerate(report['linear_frames']):
                self.assertEqual(frame['time_s'],[0,2e-7,4e-7][index])
                self.assertEqual(frame['sha256'],stream_render.file_digest(root/'stream'/frame['path']))
            normal=beam_render.Renderer(surface=surface,backend='compiled');normal.render(rows,[0,2e-7,4e-7])
            raw=(root/'stream/replay.mcrt').read_bytes();size=struct.unpack_from('<I',raw,8)[0]
            meta=json.loads(raw[12:12+size]);payload=raw[12+size:]
            self.assertEqual(meta['qualification'],'experimental-optical-bench')
            for index,chunk in enumerate(meta['chunks']):
                data=payload[chunk['offset']:chunk['offset']+chunk['bytes']]
                self.assertEqual(beam_render.digest(data),chunk['sha256'])
                if chunk['kind']=='frame':self.assertEqual(data,normal.frames[index]['display'])
            self.assertEqual(json.loads((root/'stream/optical-state.json').read_text()),normal.checkpoint())
            self.assertFalse((root/'stream/payload.pending').exists())
            with self.assertRaises(ValueError):stream_render.run(trace,root/'truncated',[0,8e-7],surface=surface)
            self.assertFalse((root/'truncated/replay.mcrt').exists())
            self.assertEqual(json.loads((root/'truncated/render.json').read_text())['status'],'incomplete')
            with patch.object(stream_render.phosphor,'png',side_effect=OSError('disk full')):
                with self.assertRaises(OSError):stream_render.run(trace,root/'failed',[0,4e-7],surface=surface)
            self.assertFalse((root/'failed/replay.mcrt').exists())

    def test_image_gate_consumes_export_and_rejects_unsettled_phosphor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);trace=root/'trace.csv'
            times=[i*2e-7 for i in range(17)]
            with trace.open('w') as stream:
                writer=csv.writer(stream);writer.writerow(beam_render.FIELDS)
                writer.writerows([row(0),row(times[-1])])
            stream_render.run(trace,root/'stream',times,surface=dict(width=32,height=24))
            result=image_acceptance.assess(root/'stream',first_frame=1)
            self.assertFalse(result['accepted'])
            self.assertFalse(result['temporal_stability'])
            self.assertGreater(result['temporal_worst']['error'],.02)


if __name__=='__main__':unittest.main()
