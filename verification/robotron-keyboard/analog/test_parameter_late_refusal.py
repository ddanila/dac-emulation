import ast
import unittest
from pathlib import Path
from build_parameter_late_refusal_bridge import refusal_header
from build_memory_bridge import PREVIOUS_HEADER
HERE=Path(__file__).resolve().parent

class LateRefusal(unittest.TestCase):
    def test_capture_only_modes_and_class_environment_change(self):
        original=(HERE/'parameter_continue_capture.py').read_text()
        changed=(HERE/'parameter_late_refusal_capture.py').read_text()
        changed=changed.replace('Capture late unsupported parameter classes and ordinary execution after refusal.','Capture restored later parameter faults followed by complete ordinary execution.')
        changed=changed.replace("modes=['parameter-late-'+n for n in ('binary','real','string')]","modes=['parameter-'+n+'-corrupt' for n in ('word','signed','sized','local','file','line','name','width','scope','name-pointer')]")
        changed=changed.replace("ROBOTRON_PRIVATE_DISPLAY=mode,ROBOTRON_PARAMETER_CLASS='none')",'ROBOTRON_PRIVATE_DISPLAY=mode)')
        self.assertEqual(ast.dump(ast.parse(changed)),ast.dump(ast.parse(original)))

    def test_compiled_candidate_boundaries(self):
        import json
        from ttl7406_probe import sha
        root=Path('/private/tmp/k7658-parameter-late-refusal-bridge')
        if not root.exists():self.skipTest('Candidate build is local')
        build=json.loads((root/'build.json').read_text())
        for n,h in build['outputs'].items():self.assertEqual(sha(root/n),h)
        source=(root/'icarus_shim.c').read_text()
        self.assertEqual(source.count('VB_PARAMETER_LATE round='),2)
        self.assertIn('if(parameter_fault_done==2)return;',source)
        self.assertIn('info->vtime<6e-6',source)
        self.assertIn('robotron_vvp_parameter_add_unsupported',source)
        self.assertNotIn('VB_PARAMETER_FAULT field=',source)

if __name__=='__main__':unittest.main()
