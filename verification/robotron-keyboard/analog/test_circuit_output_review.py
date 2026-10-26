from pathlib import Path
import tempfile
import unittest
from circuit_output_review import inventory, external_fault

FRAME = ('H_BEGIN callback-entry 0.000011\nC_SUM 2\n'
         'C_PORT 0 1 0 0 adc sense 1 0 0\nC_EVENT 0 0 0x1p-16 0x1p-17 0 0x0p+0 1 0\n'
         'C_PORT 1 2 1 1 ahdl data 0 0 1\nH_END\n')
FAULT = ('H_REJECT 0.000001 equal=1\nFIRST_FETCH 2000000 0000 af\n'
         'HISTORY_CORRUPTION time=0.000011 after=0.00001\n'
         'C_CORRUPT pending index=0 instance=adc\nH_REJECT 0.000011 equal=0\n'
         'Rejected trial changed XSPICE history\n')


class CircuitOutputTests(unittest.TestCase):
    def test_external_inventory_and_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'; path.write_text(FRAME + FAULT)
            result = inventory(path)
            self.assertEqual(result['outputs'], 2)
            self.assertEqual(result['otherModelPendingEventObservations'], 1)
            self.assertFalse(external_fault(path, .00001)['mutatedOutput']['controllerOwned'])

    def test_incomplete_inventory_and_bad_events_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            for bad in (FRAME.replace('C_SUM 2', 'C_SUM 3'), FRAME.replace('C_PORT 1', 'C_PORT 0'),
                        FRAME.replace('C_EVENT 0 0', 'C_EVENT 1 0'), FRAME.replace('C_EVENT 0 0', 'C_EVENT 0 2'),
                        FRAME.replace('1 0 0\nC_EVENT', '2 0 0\nC_EVENT'), FRAME.replace('H_END\n', ''),
                        FRAME + FRAME.replace('adc sense', 'other sense')):
                path.write_text(bad)
                with self.assertRaises(ValueError): inventory(path)

    def test_controller_or_unobserved_mutation_cannot_claim_external_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'log'
            for bad in (FAULT.replace('index=0 instance=adc', 'index=1 instance=ahdl'),
                        FAULT.replace('index=0 instance=adc', 'index=9 instance=unknown'),
                        FAULT.replace('instance=adc', 'instance=wrong')):
                path.write_text(FRAME + bad)
                with self.assertRaises(ValueError): external_fault(path, .00001)


if __name__ == '__main__': unittest.main()
