import json,lzma,tempfile,unittest
from pathlib import Path
import memory_late_prefix as combined
from retained_evidence import check
from memory_board_budget import native_layout
ROOT=Path(__file__).resolve().parent/'reports/memory-late-controls'

class MemoryLateTests(unittest.TestCase):
    def test_retained_later_faults(self):
        check(ROOT);r=combined.review(ROOT)
        self.assertEqual(json.loads(json.dumps(r)),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(len(r['negativeControls']),5)
        for value in r['negativeControls'].values():
            self.assertEqual(value['boundaries'],2)
            self.assertGreaterEqual(value['fault']['targetSeconds'],5e-6)
            self.assertGreater(value['fault']['index'],0)
            self.assertEqual(value['scopeMetadata']['memories'],3)
        for prefix in r['referencePrefixes'].values():
            self.assertEqual(prefix['samples'],18959)
            self.assertEqual(len(prefix['signals']),31)
    def run_log(self,text,mode='memory-name-corrupt'):
        run=json.loads((ROOT/mode/'run.json').read_text());ids=combined.preflight.verify_symbols(ROOT,{'off':run});compiled=(ROOT/'baseline/io.vvp').read_text()
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'ngspice.log';p.write_text(text)
            return combined.inventory(p,ids,fault_type=mode.removesuffix('-corrupt'),contract=combined.preflight.port_contract(compiled),compiled=compiled,memory_offset=native_layout(ROOT))
    def test_early_wrong_phase_and_startup_index_reject(self):
        text=lzma.decompress((ROOT/'memory-name-corrupt/ngspice.log.xz').read_bytes()).decode()
        original=[s for s in text.splitlines() if s.startswith('VB_BRIDGE ')][1];words=original.split()
        for index,value in [(1,'0'),(2,'after-step'),(3,'0.000001')]:
            changed=words.copy();changed[index]=value
            with self.subTest(index=index),self.assertRaises(ValueError):self.run_log(text.replace(original,' '.join(changed),1))
    def test_missing_refusal_or_restoration_reject(self):
        for mode,old,new in [('memory-storage-pointer-corrupt','rejected=1 restored=1','rejected=0 restored=1'),('memory-name-corrupt','VB_STAGE restored','VB_STAGE changed')]:
            text=lzma.decompress((ROOT/mode/'ngspice.log.xz').read_bytes()).decode();self.assertIn(old,text)
            with self.subTest(mode=mode),self.assertRaises(ValueError):self.run_log(text.replace(old,new,1),mode)

    def test_prefix_count_and_data_corruption_reject(self):
        from trace_io import open_binary
        mode='memory-name-corrupt'
        boundary=json.loads((ROOT/'assessment.json').read_text())['negativeControls'][mode]['fault']
        with open_binary(ROOT/mode/'waveform.raw') as f:data=f.read()
        for changed in (data[:-1],data[:-8]+bytes([data[-8]^1])+data[-7:]):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/'waveform.raw';p.write_bytes(changed)
                with self.assertRaises(ValueError):combined.compare_prefix(p,ROOT/'baseline/waveform.raw',boundary)
        with self.assertRaises(ValueError):combined.compare_prefix(ROOT/mode/'waveform.raw',ROOT/'baseline/waveform.raw',dict(boundary,index=boundary['index']+2))

if __name__=='__main__':unittest.main()
