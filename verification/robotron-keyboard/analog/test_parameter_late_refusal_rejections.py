import json,os,tempfile,unittest
from pathlib import Path
from trace_io import open_binary
from parameter_late_refusal_review import inventory
from parameter_late_refusal_preflight import verify_symbols,port_contract
from memory_board_budget import native_layout
HERE=Path(__file__).resolve().parent

class RefusalRejections(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(os.environ.get('ROBOTRON_PARAMETER_LATE_REFUSAL_REPORT',HERE/'reports/parameter-late-refusal-controls'))
        path=root/'parameter-late-binary/run.json'
        if not path.exists():raise unittest.SkipTest('Completed binary control not available')
        receipt=json.loads(path.read_text())
        if not receipt.get('completed'):raise unittest.SkipTest('Binary control still running')
        compiled=(root/'baseline/io.vvp').read_text()
        cls.identities=verify_symbols(root,{'off':receipt})
        cls.kwargs=dict(fault_type='parameter-late-binary',contract=port_contract(compiled),compiled=compiled,memory_offset=native_layout(root))
        with open_binary(path.parent/'ngspice.log') as f:cls.lines=f.read().decode().splitlines()

    def review_lines(self,lines):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log';p.write_text('\n'.join(lines)+'\n');return inventory(p,self.identities,**self.kwargs)

    def test_missing_later_refusal(self):
        lines=[l for l in self.lines if not l.startswith('VB_PARAMETER_LATE round=2 ')]
        with self.assertRaisesRegex(ValueError,'Missing immediate/later refusal'):self.review_lines(lines)

    def test_failed_refusal_or_cache_change(self):
        for field in ('refused','cache_unchanged'):
            lines=[l.replace(field+'=1',field+'=0') if l.startswith('VB_PARAMETER_LATE ') else l for l in self.lines]
            with self.assertRaisesRegex(ValueError,'Invalid late refusal'):self.review_lines(lines)

    def test_serialized_state_after_refusal(self):
        lines=self.lines.copy();i=next(i for i,l in enumerate(lines) if l.startswith('VB_PARAMETER_LATE round=1 '))
        lines.insert(i+1,'VPMD_BEGIN 1 5000000 4 0 1')
        with self.assertRaisesRegex(ValueError,'Metadata outside snapshot stage'):self.review_lines(lines)

if __name__=='__main__':unittest.main()
