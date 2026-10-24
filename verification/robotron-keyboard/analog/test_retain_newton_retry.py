from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from retain_newton_retry import retain,check
from test_newton_retry_review import fixture


class RetentionTests(unittest.TestCase):
    def test_retention_rechecks_evidence_and_rejects_mutation(self):
        with tempfile.TemporaryDirectory() as tmp,patch('newton_retry_review.check_bridge'):
            root=Path(tmp);pair,control,evidence=fixture(root)
            (pair/'capture-generator.py').write_text('# test producer\n')
            out=root/'retained';retain(pair,control,evidence,out);check(out)
            self.assertFalse((out/'on/waveform.raw').exists())
            with self.assertRaises(FileExistsError):retain(pair,control,evidence,out)
            (out/'on/ngspice.log.xz').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError,'Changed retained'):check(out)


if __name__=='__main__':unittest.main()
