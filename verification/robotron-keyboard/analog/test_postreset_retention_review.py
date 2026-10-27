import hashlib
import lzma
from pathlib import Path
import tempfile
import unittest

from postreset_retention_review import verify_archive


class ArchiveIdentityTests(unittest.TestCase):
    def test_content_identity_and_bounded_size(self):
        original=b'waveform and authentic log bytes\x00\xff'*3000
        receipt=dict(bytes=len(original),sha256=hashlib.sha256(original).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'archive.xz'
            for name,data in (('original',original),('same-size',b'X'+original[1:]),
                              ('short',original[:-1]),('long',original+b'X')):
                with self.subTest(name=name):
                    path.write_bytes(lzma.compress(data))
                    if name=='original':
                        verify_archive(path,receipt)
                    else:
                        with self.assertRaises(ValueError):verify_archive(path,receipt)

    def test_invalid_or_truncated_container_is_refused(self):
        data=b'retained evidence'
        receipt=dict(bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'archive.xz'
            for broken in (b'invalid container',lzma.compress(data)[:-5]):
                path.write_bytes(broken)
                with self.assertRaises((lzma.LZMAError,EOFError)):
                    verify_archive(path,receipt)


if __name__=='__main__':unittest.main()
