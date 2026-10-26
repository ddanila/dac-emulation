import shutil
import tempfile
import unittest
from pathlib import Path
from private_queue_probe import HERE, review, snapshot

ROOT=HERE/'reports/private-hdl-queue'


class QueueProbeTests(unittest.TestCase):
    def test_retained_controls_cover_observation_and_restored_faults(self):
        r=review(ROOT)
        self.assertFalse(r['qualified'])
        self.assertEqual(r['timeMutationsDetectedAndRestored'],3)

    def test_incomplete_misordered_and_shifted_snapshots_rejected(self):
        lines=(ROOT/'enabled.stdout').read_text().splitlines()
        start=next(i for i,l in enumerate(lines) if l.startswith('VQ_BEGIN'))
        end=next(i for i,l in enumerate(lines[start:],start) if l.startswith('VQ_END'))
        original=lines[start:end+1];snapshot(original)
        for marker,replacement in [('VQ_COUNT -1 init 0',None),
                                   ('VQ_TIME 0 0 2000','VQ_TIME 0 0 2001')]:
            bad=[replacement if l==marker else l for l in original if l!=marker or replacement is not None]
            with self.assertRaises(ValueError):snapshot(bad)
        index=next(i for i,l in enumerate(original) if l.startswith('VQ_EVENT'))
        bad=original[:];fields=bad[index].split();fields[3]='1';bad[index]=' '.join(fields)
        with self.assertRaises(ValueError):snapshot(bad)

    def test_disabled_observer_cannot_change_output_or_masquerade_as_baseline(self):
        for replacement in ('VALUE unexpected\n',None):
            with tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)
                for p in ROOT.glob('*.stdout'):shutil.copyfile(p,out/p.name)
                for p in ROOT.glob('*.stderr'):shutil.copyfile(p,out/p.name)
                p=out/'disabled.stdout';s=p.read_text()
                p.write_text(s+replacement if replacement else s.replace('VQ_API 1','VQ_API 0'))
                with self.assertRaises(ValueError):review(out)


if __name__=='__main__':unittest.main()
