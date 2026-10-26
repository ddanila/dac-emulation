import shutil
import tempfile
import unittest
from pathlib import Path
from private_sync_probe import HERE, review, snapshot

ROOT=HERE/'reports/private-hdl-sync'


class SyncProbeTests(unittest.TestCase):
    def test_retained_matched_controls(self):
        result=review(ROOT)
        self.assertFalse(result['qualified'])
        self.assertEqual(result['modeMutationsDetectedAndRestored'],6)
        self.assertEqual(result['executingObservations'],12)

    def test_unknown_referents_and_incomplete_registry_rejected(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines()
        start=next(i for i,l in enumerate(lines) if l.startswith('VS_BEGIN'))
        end=next(i for i,l in enumerate(lines[start:],start) if l=='VS_END')
        original=lines[start:end+1];snapshot(original)
        for index in (7,8,9,10,11,12,13):
            with self.subTest(field=index):
                bad=original[:];fields=bad[1].split();fields[index]='0';bad[1]=' '.join(fields)
                with self.assertRaises(ValueError):snapshot(bad)
        with self.assertRaises(ValueError):snapshot(original[:1]+original[2:])

    def test_missing_executing_state_cancellation_or_fault_is_rejected(self):
        changes=[('enabled.stdout','VS_CALLBACK 1 1 0','VS_CALLBACK 1 0 0'),
                 ('enabled.stdout','VS_CALLBACK 2 0 0 9 2 0 0','VS_CALLBACK 2 0 0 9 2 1 1'),
                 ('corrupt.stdout','VS_FAULT 1','VS_FAULT 0'),
                 ('disabled.stdout','VS_API 1','VS_API 0'),
                 ('enabled.stdout','VS_BEGIN 1 3000 4','VS_BEGIN 1 3000 3'),
                 ('disabled.stdout','CALLBACK 0 3000 1','CALLBACK 0 3001 1')]
        for filename,before,after in changes:
            with self.subTest(change=before),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                for pattern in ('*.stdout','*.stderr'):
                    for source in ROOT.glob(pattern):shutil.copyfile(source,out/source.name)
                p=out/filename;s=p.read_text();self.assertIn(before,s);p.write_text(s.replace(before,after,1))
                with self.assertRaises(ValueError):review(out)


if __name__=='__main__':unittest.main()
