import array
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import image_acceptance as gate
import phosphor


class ImageAcceptanceTests(unittest.TestCase):
    def archive(self, root, *, scale=1, change=None):
        root.mkdir()
        p = phosphor.parameters(dict(width=8*scale, height=8*scale))
        frames = []
        for i in range(16):
            pixels = [1. if x//scale < 4 else 2. for y in range(8*scale) for x in range(8*scale)]
            if change:
                pixels = change(i, pixels)
            data = array.array('f', pixels)
            if sys.byteorder != 'little':
                data.byteswap()
            name = f'frame-{i:03d}.f32'
            (root/name).write_bytes(data.tobytes())
            frames.append(dict(path=name, time_s=(i+1)*.02, sha256=gate.digest(root/name)))
        (root/'input.csv').write_text('synthetic test fixture, not a connected circuit\n')
        report = dict(status='complete', frames=16, linear_frames=frames, surface_parameters=p,
                      hashes={'input.csv': gate.digest(root/'input.csv')},
                      linear_format=dict(dtype='little-endian float32', unit='W/m^2',
                                         order='row-major', width=8*scale, height=8*scale))
        (root/'render.json').write_text(json.dumps(report))
        return report

    def test_identical_frames_need_refinement_and_do_not_qualify_monitor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root/'base')
            self.archive(root/'fine', scale=2)
            report = gate.assess(root/'base')
            self.assertTrue(report['temporal_stability'])
            self.assertFalse(report['accepted'])
            report = gate.assess(root/'base', refined=root/'fine')
            self.assertTrue(report['accepted'])
            self.assertFalse(report['full_monitor_qualified'])
            self.assertFalse(report['source_content_verified'])
            self.assertFalse(report['electrical_refinement_verified'])

    def test_detects_slow_drift_and_motion_with_unchanged_average(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root/'drift', change=lambda i, p: [x*(1+.003*i) for x in p])
            report = gate.assess(root/'drift')
            self.assertFalse(report['temporal_stability'])
            self.assertEqual(report['temporal_worst']['frames'], [0, 15])
            self.archive(root/'motion', change=lambda i, p: p if i < 15 else p[::-1])
            self.assertFalse(gate.assess(root/'motion')['temporal_stability'])

    def test_refinement_rejects_brightness_fit_and_wrong_geometry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root/'base')
            self.archive(root/'fine', scale=2, change=lambda i, p: [x*1.03 for x in p])
            self.assertFalse(gate.assess(root/'base', refined=root/'fine')['spatial_refinement'])
            self.archive(root/'jitter', scale=2,
                         change=lambda i, p: [x*(1.015 if i % 2 else .985) for x in p])
            report = gate.assess(root/'base', refined=root/'jitter')
            self.assertTrue(report['spatial_refinement'])
            self.assertFalse(report['temporal_stability'])
            self.assertFalse(report['accepted'])
            data = self.archive(root/'badscale', scale=1)
            with self.assertRaisesRegex(ValueError, 'uniform scale'):
                gate.assess(root/'base', refined=root/'badscale')
            data['surface_parameters']['screen_width_m'] *= 1.01
            (root/'badscale/render.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'parameters changed'):
                gate.assess(root/'base', refined=root/'badscale')

    def test_rejects_invalid_artifacts_and_wrong_times(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root/'base')
            data = self.archive(root/'fine', scale=2)
            data['linear_frames'][-1]['time_s'] += .00001
            (root/'fine/render.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'times differ'):
                gate.assess(root/'base', refined=root/'fine')
            (root/'base/frame-015.f32').write_bytes(b'broken')
            with self.assertRaisesRegex(ValueError, 'size or hash'):
                gate.assess(root/'base')
            for name, value in [('dark', 0.), ('nan', float('nan')), ('negative', -1.)]:
                self.archive(root/name, change=lambda i, p: [value]*len(p))
                with self.assertRaises(ValueError):
                    gate.assess(root/name)

    def test_requires_distinct_frames_input_integrity_and_original_indices(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = self.archive(root/'base')
            for index in (-1, 1, True):
                with self.assertRaises(ValueError):
                    gate.assess(root/'base', first_frame=index)
            data['linear_frames'][-1] = data['linear_frames'][0]
            (root/'base/render.json').write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                gate.assess(root/'base')
            self.archive(root/'corrupt')
            (root/'corrupt/input.csv').write_text('different input')
            with self.assertRaisesRegex(ValueError, 'input or model hash'):
                gate.assess(root/'corrupt')

    def test_spatial_projection_conserves_optical_power(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self.archive(root/'base')
            self.archive(root/'fine', scale=2)
            base, fine = gate.Archive(root/'base', 0), gate.Archive(root/'fine', 0)
            pixels = fine.read(0)
            projected = gate.project(pixels, fine, base)
            self.assertAlmostEqual(sum(v*a for v, a in zip(pixels, fine.areas)),
                                   sum(v*a for v, a in zip(projected, base.areas)), places=14)


if __name__ == '__main__':
    unittest.main()
