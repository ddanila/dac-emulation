from pathlib import Path
import tempfile
import unittest
from instance_queue_review import inventory,external_fault,runtime_summary

FRAME=('H_BEGIN run-entry 0.000011\nI_SUM 2 0x1p-20 0x1p-15 0 1 0\n'
       'I_INDEX 1 0 0\nI_INST 0 0 adc 0 1 0\n'
       'I_SLOT 0 0 0 1 1\nI_EVENT 0 0 0x1p-20 0x0p+0\n'
       'I_SLOT 0 1 1 0 1\nI_EVENT 0 1 0x1p-15 0x1p-16\n'
       'I_SLOT 0 2 0 0 0\nI_INST 1 1 ahdl 0 0 0\nI_SLOT 1 0 1 1 0\nH_END\n')
FAULT=('H_REJECT 0.000001 equal=1\nFIRST_FETCH 2000000 0000 af\n'
       'HISTORY_CORRUPTION time=0.000011 after=0.00001\n'
       'C_CORRUPT instance-current index=0 instance=adc from=1 to=0\n'
       'H_REJECT 0.000011 equal=0\nRejected trial changed XSPICE history\n')


class InstanceQueueTests(unittest.TestCase):
    def test_complete_inventory_and_external_anchor_fault(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log';p.write_text(FRAME+FAULT)
            data=inventory(p)
            self.assertEqual(data['externalPendingEventObservations'],1)
            self.assertEqual(data['eventObservations'],2)
            self.assertEqual(data['lastAnchors'][0],{'index':0,'current':1,'lastStep':0,'events':2})
            self.assertEqual(external_fault(p,1e-5)['previousCurrentOrdinal'],1)

    def test_missing_reordered_or_invalid_queue_records_fail(self):
        changes=[('I_SUM 2','I_SUM 3'),('I_INDEX 1 0 0','I_INDEX 1 1 0'),
                 ('I_INDEX 1 0 0','I_INDEX 1 0 2'),('I_INST 1','I_INST 0'),
                 ('I_SLOT 0 1 1 0 1','I_SLOT 0 1 0 0 1'),
                 ('I_SLOT 0 2 0 0 0','I_SLOT 0 2 1 0 0'),
                 ('I_SLOT 0 2 0 0 0','I_SLOT 0 2 0 0 1'),
                 ('I_EVENT 0 1','I_EVENT 0 0'),('0x1p-15 0x1p-16','0x1p-21 0x1p-22'),
                 ('0x1p-15 0x1p-16','nan 0x1p-16'),('0x1p-15 0x1p-16','0x1p-15 0x1p-14'),
                 ('I_INST 0 0 adc 0 1 0','I_INST 0 0 adc 0 2 0'),('H_END\n','')]
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log'
            for old,new in changes:
                with self.subTest(new=new):
                    p.write_text(FRAME.replace(old,new))
                    with self.assertRaises(ValueError):inventory(p)
            p.write_text(FRAME+FRAME.replace('adc','other'))
            with self.assertRaises(ValueError):inventory(p)

    def test_unobserved_or_controller_fault_cannot_claim_external_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log'
            for old,new in [('index=0 instance=adc','index=1 instance=ahdl'),
                            ('index=0','index=7'),('instance=adc','instance=other'),
                            ('from=1','from=0'),('from=1','from=2')]:
                p.write_text(FRAME+FAULT.replace(old,new))
                with self.assertRaises(ValueError):external_fault(p,1e-5)

    def test_structural_records_do_not_hide_producer_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log';p.write_text(FRAME+'No. of Data Rows : 2\n')
            self.assertEqual(runtime_summary(p),{'count':2,'diagnostic':None,'sorry':False})
            p.write_text(FRAME+'No. of Data Rows : 2\nError: timestep too small\n')
            self.assertTrue(runtime_summary(p)['diagnostic'])
            for suffix in [FAULT,'No. of Data Rows : 3\n']:
                p.write_text(FRAME+'No. of Data Rows : 2\n'+suffix)
                with self.assertRaises(ValueError):runtime_summary(p)


if __name__=='__main__':unittest.main()
