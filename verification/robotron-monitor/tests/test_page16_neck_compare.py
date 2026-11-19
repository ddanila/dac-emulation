import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import page16_neck_compare as neck
import inventory_audit
import reference


class Page16NeckCompareTests(unittest.TestCase):
    def test_source_pins_match_fresh_kicad_and_diode_reversal_is_detected(self):
        pdf=ROOT.parents[1]/'build/monitor/phase-a/sources/older.pdf'
        report=neck.run(pdf)
        self.assertTrue(report['passed'])
        self.assertEqual(report['source_component_pins'],39)
        self.assertEqual(report['source_connector_pins'],17)
        self.assertEqual(report['matched_connector_pins'],17)
        self.assertEqual(report['diode_directions_checked'],6)
        source=json.loads(neck.SOURCE.read_text())
        assembly=json.loads(neck.ASSEMBLY.read_text())
        with tempfile.TemporaryDirectory() as directory:
            xml=Path(directory)/'netlist.xml'
            import subprocess
            subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                            '-o',str(xml),str(neck.SHEET)],check=True,capture_output=True)
            tree=ET.parse(xml)
            d5=[node for node in tree.findall('./nets/net/node') if node.get('ref')=='D5']
            self.assertEqual(len(d5),2)
            a,b=d5[0].get('pin'),d5[1].get('pin')
            d5[0].set('pin',b);d5[1].set('pin',a)
            tree.write(xml)
            changed=neck.compare(source,assembly,xml,source_pdf_sha256=report['source_pdf_sha256'],
                                 sheet_sha256=report['sheet_sha256'])
            self.assertFalse(changed['passed'])
            self.assertEqual({row['source_id'] for row in changed['missing_or_changed_pins']},
                             {'012-6891:V2:5'})
            subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                            '-o',str(xml),str(neck.SHEET)],check=True,capture_output=True)
            tree=ET.parse(xml)
            j2=[node for node in tree.findall('./nets/net/node') if node.get('ref')=='J2'
                and node.get('pin') in ('2','3')]
            self.assertEqual(len(j2),2)
            j2[0].set('pin','3');j2[1].set('pin','2')
            tree.write(xml)
            changed=neck.compare(source,assembly,xml,source_pdf_sha256=report['source_pdf_sha256'],
                                 sheet_sha256=report['sheet_sha256'])
            self.assertFalse(changed['passed'])
            self.assertEqual({row['pin'] for row in changed['missing_or_changed_connector_pins']},
                             {'2','3'})
            inventory=json.loads(inventory_audit.INVENTORY.read_text())
            with self.assertRaisesRegex(ValueError,'connector pins differ'):
                reference.source_connectivity(xml,inventory,'012-6891')
        changed=copy.deepcopy(assembly)
        changed['neck_connectors']['X2']['2']='0'
        with tempfile.TemporaryDirectory() as directory:
            xml=Path(directory)/'netlist.xml'
            import subprocess
            subprocess.run(['kicad-cli','sch','export','netlist','--format','kicadxml',
                            '-o',str(xml),str(neck.SHEET)],check=True,capture_output=True)
            with self.assertRaisesRegex(ValueError,'connector pins differ'):
                neck.compare(source,changed,xml,
                    source_pdf_sha256=report['source_pdf_sha256'],sheet_sha256=report['sheet_sha256'])


if __name__=='__main__':unittest.main()
