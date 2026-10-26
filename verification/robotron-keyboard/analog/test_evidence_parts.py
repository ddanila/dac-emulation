import hashlib,json,tempfile,unittest
from pathlib import Path
from evidence_parts import pack,restore

class EvidencePartsTests(unittest.TestCase):
    def test_exact_binary_and_empty_round_trip(self):
        for data in (bytes(range(256))*7,b''):
            with tempfile.TemporaryDirectory() as d:
                root=Path(d);source=root/'trace.raw.xz';source.write_bytes(data)
                m=pack(source,root/'parts',73)
                self.assertTrue(all(p['bytes']<=73 for p in m['parts']))
                self.assertEqual(m['sha256'],hashlib.sha256(data).hexdigest())
                restore(root/'parts',root/'restored')
                self.assertEqual((root/'restored').read_bytes(),data)
                with self.assertRaises(FileExistsError):restore(root/'parts',root/'restored')
                self.assertEqual((root/'restored').read_bytes(),data)

    def test_corruption_truncation_and_missing_parts_never_publish(self):
        for change in ('corrupt','truncate','missing','omit'):
            with tempfile.TemporaryDirectory() as d:
                r=Path(d);(r/'source').write_bytes(b'abcdefghij');m=pack(r/'source',r/'parts',4)
                part=r/'parts/part-000001'
                if change=='corrupt':part.write_bytes(b'WXYZ')
                elif change=='truncate':part.write_bytes(b'e')
                elif change=='missing':part.unlink()
                else:
                    m['parts'].pop();(r/'parts/manifest.json').write_text(json.dumps(m))
                with self.assertRaises((ValueError,FileNotFoundError)):restore(r/'parts',r/'restored')
                self.assertFalse((r/'restored').exists())
                self.assertFalse(list(r.glob('.evidence-*')))

    def test_part_paths_are_not_trusted(self):
        with tempfile.TemporaryDirectory() as d:
            r=Path(d);(r/'source').write_bytes(b'data');m=pack(r/'source',r/'parts',4)
            m['parts'][0]['name']='../source';(r/'parts/manifest.json').write_text(json.dumps(m))
            with self.assertRaises(ValueError):restore(r/'parts',r/'restored')
            self.assertFalse((r/'restored').exists())

if __name__=='__main__':unittest.main()
