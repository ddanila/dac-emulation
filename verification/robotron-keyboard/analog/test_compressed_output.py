import hashlib
import lzma
import tempfile
import subprocess
import sys
import shutil
import unittest
from unittest.mock import patch
from pathlib import Path
from compressed_output import capture


class CompressedOutputTests(unittest.TestCase):
    def test_multiple_streams_preserve_exact_bytes_and_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            data = b'time voltage\n' + b'1.00000000e-09 5.00000000e+00\n' * 100000
            with capture(p, ['trace.txt', 'led-trace.txt']) as records:
                for name in ('trace.txt', 'led-trace.txt'):
                    with (p / name).open('wb') as stream:
                        stream.write(data)
            for name in ('trace.txt', 'led-trace.txt'):
                self.assertFalse((p / name).exists())
                self.assertEqual(lzma.decompress((p / (name + '.xz')).read_bytes()), data)
                self.assertEqual(records[name], {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})

    def test_subprocess_stdout_with_raw_stream_and_failed_producer(self):
        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as directory:
                p=Path(directory)
                script="import sys; from pathlib import Path; print('audit start',flush=True); Path('waveform.raw').write_bytes(b'raw bytes'); print('audit end',flush=True); sys.exit(%d)" % (7 if fail else 0)
                def run():
                    with capture(p,['waveform.raw','ngspice.log']) as records:
                        with (p/'ngspice.log').open('w') as log:
                            subprocess.run([sys.executable,'-c',script],cwd=p,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=10)
                    return records
                if fail:
                    with self.assertRaises(subprocess.CalledProcessError):run()
                    self.assertFalse((p/'ngspice.log.xz').exists())
                    self.assertFalse((p/'waveform.raw.xz').exists())
                else:
                    records=run()
                    self.assertEqual(lzma.decompress((p/'ngspice.log.xz').read_bytes()),b'audit start\naudit end\n')
                    self.assertEqual(records['ngspice.log']['bytes'],len(b'audit start\naudit end\n'))
                    self.assertEqual(lzma.decompress((p/'waveform.raw.xz').read_bytes()),b'raw bytes')

    def test_timeout_does_not_publish_partial_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            with self.assertRaises(subprocess.TimeoutExpired):
                with capture(p,['waveform.raw','ngspice.log']):
                    with (p/'ngspice.log').open('w') as log:
                        subprocess.run([sys.executable,'-c',"import time; print('started',flush=True); time.sleep(10)"],cwd=p,stdout=log,stderr=subprocess.STDOUT,timeout=.1)
            self.assertFalse((p/'ngspice.log.xz').exists())
            self.assertFalse((p/'waveform.raw.xz').exists())
            self.assertFalse((p/'ngspice.log').exists())

    @unittest.skipUnless(shutil.which('ngspice'), 'ngspice is required')
    def test_ngspice_can_write_waveform_and_stdout_fifos_together(self):
        from audit_log import scan
        from trace_io import open_text
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)
            (p/'io.cir').write_text('RC transport\nV1 in 0 PULSE(0 5 1n 1n 1n 10n 20n)\nR1 in out 1k\nC1 out 0 1p\n.tran .1n 40n\n.control\nrun\nwrdata trace.txt v(out)\nquit\n.endc\n.end\n')
            with capture(p,['trace.txt','ngspice.log']) as records:
                with (p/'ngspice.log').open('w') as log:
                    subprocess.run(['ngspice','-n','-b','io.cir'],cwd=p,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=20)
            summary=scan(p/'ngspice.log')
            self.assertIsNone(summary['diagnostic']);self.assertGreater(summary['count'],0)
            with open_text(p/'trace.txt') as stream:
                samples=[list(map(float,line.split())) for line in stream]
            self.assertEqual(len(samples),summary['count'])
            self.assertAlmostEqual(samples[-1][0],40e-9)
            self.assertIn('ngspice.log',records)

    def test_selected_presets_preserve_identical_producer_bytes(self):
        data = b'time voltage\n' + bytes(range(256)) * 10000
        for preset in (0, 6):
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as directory:
                p = Path(directory)
                with capture(p, ['trace.txt'], preset=preset) as records:
                    (p / 'trace.txt').write_bytes(data)
                self.assertEqual(lzma.decompress((p / 'trace.txt.xz').read_bytes()), data)
                self.assertEqual(records['trace.txt']['sha256'], hashlib.sha256(data).hexdigest())
                self.assertEqual(records['trace.txt']['bytes'], len(data))

    def test_invalid_preset_creates_no_outputs(self):
        for preset in (-1, 10, 1.5, True, None):
            with self.subTest(preset=preset), tempfile.TemporaryDirectory() as directory:
                p = Path(directory)
                with self.assertRaisesRegex(ValueError, 'XZ preset'):
                    with capture(p, ['trace.txt'], preset=preset):
                        self.fail('Invalid preset accepted')
                self.assertEqual(list(p.iterdir()), [])

    def test_failed_producer_cleans_up_waiting_readers(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            with self.assertRaisesRegex(RuntimeError, 'producer failed'):
                with capture(p, ['trace.txt']):
                    raise RuntimeError('producer failed')
            self.assertFalse((p / 'trace.txt').exists())
            self.assertFalse((p / 'trace.txt.xz').exists())

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            (p / 'trace.txt.xz').write_bytes(b'old evidence')
            with self.assertRaisesRegex(ValueError, 'fresh output'):
                with capture(p, ['trace.txt']):
                    self.fail('Capture accepted existing output')
            self.assertEqual((p / 'trace.txt.xz').read_bytes(), b'old evidence')

    def test_empty_output_is_not_published(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory)
            with self.assertRaisesRegex(ValueError, 'Empty compressed'):
                with capture(p, ['trace.txt']):
                    with (p / 'trace.txt').open('wb'):
                        pass
            self.assertFalse((p / 'trace.txt.xz').exists())
            self.assertFalse((p / 'trace.txt').exists())

    def test_failed_compressor_is_not_published(self):
        worker = "import sys; open(sys.argv[1], 'rb').read(); raise RuntimeError('compressor failed')"
        with tempfile.TemporaryDirectory() as directory, patch('compressed_output.WORKER', worker):
            p = Path(directory)
            with self.assertRaisesRegex(ValueError, 'compression failed'):
                with capture(p, ['trace.txt']):
                    with (p / 'trace.txt').open('wb') as stream:
                        stream.write(b'waveform')
            self.assertFalse((p / 'trace.txt.xz').exists())
            self.assertFalse((p / 'trace.txt').exists())


if __name__ == '__main__':
    unittest.main()
