import ast,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent

class PostresetDelivery(unittest.TestCase):
    def test_only_bounded_qualification_and_provenance_change(self):
        original=(HERE/'postreset_drain_capture.py').read_text()
        candidate=(HERE/'postreset_delivery_capture.py').read_text()
        candidate=candidate.replace('Capture the full post-reset delivery audit after exact bounded controls.','Capture complete ADC-enabled post-reset controls for same-tick output draining.')
        candidate=candidate.replace("SOURCES=('postreset_delivery_capture.py','delivery_audit_review.py','output_drain_board_review.py','raw_pair_review.py','postreset_refinement_capture.py','postreset_startup_review.py',","SOURCES=('postreset_drain_capture.py','postreset_refinement_capture.py','postreset_startup_review.py',")
        a=original.index('    if sha(a.bounded_assessment)!=');b=original.index("    if not bounded.get('completed')",a)
        c=candidate.index('    from delivery_audit_review import assess');d=candidate.index("    if not bounded.get('completed')",c)
        gate=candidate[c:d]
        self.assertIn('reviewed=assess(a.bounded_root)',gate)
        self.assertIn('reviewed!=json.loads(a.bounded_assessment.read_text())',gate)
        candidate=candidate[:c]+original[a:b]+candidate[d:]
        self.assertEqual(ast.dump(ast.parse(candidate)),ast.dump(ast.parse(original)))

if __name__=='__main__':unittest.main()
