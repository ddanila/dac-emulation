import hashlib
import lzma
import tempfile
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
