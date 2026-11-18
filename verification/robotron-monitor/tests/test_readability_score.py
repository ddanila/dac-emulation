import array
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import readability_score
import scan_diagnostics
import steady_supply


class ReadabilityScoreTests(unittest.TestCase):
    def test_native_text_correlates_after_global_fit_but_mirror_does_not(self):
        archive=ROOT/'examples/phase-a-native-full-text/capture.json.gz'
        capture=json.loads(gzip.decompress(archive.read_bytes()))
        selection=steady_supply.select(capture)
        source,logical=scan_diagnostics.source_summary(selection)
        width,height=source['width'],source['height']
        render_width,render_height=480,360
        def rendered(mirror):
            pixels=[]
            for row in range(render_height):
                for col in range(render_width):
                    x=(col+.5)/render_width;y=(row+.5)/render_height
                    u=1-x if mirror else (x-.03)/.95
                    v=y if mirror else (y-.02)/.96
                    pixels.append(sum(readability_score._sample(logical,width,height,u+dx/width,v+dy/height)
                                      for dy in (-.4,0,.4) for dx in (-.4,0,.4))/2295)
            return pixels
        readable=rendered(False)
        matched=readability_score.correlate(logical,width,height,readable,render_width,render_height)
        mirrored=readability_score.correlate(logical,width,height,rendered(True),render_width,render_height)
        self.assertGreater(matched['correlation'],.7)
        self.assertLess(mirrored['correlation'],.7)
        self.assertTrue(matched['one_global_affine_fit'])
        self.assertFalse(matched['fit_applied_to_render'])
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            frame=root/'frame.f32';frame.write_bytes(array.array('f',readable).tobytes())
            source_path=root/'input.csv';source_path.write_bytes(b'fixture')
            report={'format':'dac-periodic-frame-v1','status':'complete',
                    'hashes':{'input.csv':hashlib.sha256(source_path.read_bytes()).hexdigest()},
                    'outputs':{'frame.f32':{'path':'frame.f32','sha256':hashlib.sha256(frame.read_bytes()).hexdigest()}},
                    'linear_format':{'dtype':'little-endian float32','order':'row-major',
                                     'width':render_width,'height':render_height},
                    'render':{'parameters':{'width':render_width,'height':render_height}}}
            (root/'frame.json').write_text(json.dumps(report))
            self.assertGreater(readability_score.score(selection,root)['correlation'],.7)

    def test_linear_archive_hash_and_dark_frame_are_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            pixels=array.array('f',[1.]*16*16)
            frame=root/'frame.f32';frame.write_bytes(pixels.tobytes())
            source=root/'input.csv';source.write_bytes(b'fixture')
            report={'format':'dac-periodic-frame-v1','status':'complete',
                    'hashes':{'input.csv':hashlib.sha256(source.read_bytes()).hexdigest()},
                    'outputs':{'frame.f32':{'path':'frame.f32','sha256':hashlib.sha256(frame.read_bytes()).hexdigest()}},
                    'linear_format':{'dtype':'little-endian float32','order':'row-major','width':16,'height':16},
                    'render':{'parameters':{'width':16,'height':16}}}
            (root/'frame.json').write_text(json.dumps(report))
            self.assertEqual(readability_score.read_archive(root)[:2],(16,16))
            frame.write_bytes(array.array('f',[0.]*16*16).tobytes())
            with self.assertRaisesRegex(ValueError,'linear frame hash mismatch'):
                readability_score.read_archive(root)
            report['outputs']['frame.f32']['sha256']=hashlib.sha256(frame.read_bytes()).hexdigest()
            (root/'frame.json').write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'invalid or dark'):
                readability_score.read_archive(root)


if __name__=='__main__':unittest.main()
