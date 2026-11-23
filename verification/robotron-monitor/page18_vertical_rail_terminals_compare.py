"""Compare the page-18 X21/X22 rail terminal labels with an audit-only export."""
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from page18_vertical_cable_compare import physical_pins

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SOURCE = REF / 'page18-interconnect-transcription.json'
SHEET = ROOT / 'circuits/k7222-11-page18-vertical-rail-terminals.kicad_sch'
OUTPUT = REF / 'page18-vertical-rail-terminals-comparison.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if source['source']['pdf_sha256'] != sha(source_pdf):
        raise ValueError('page-18 source PDF changed')
    expected = {'012-6931:X21': {'1': '12P'}, '012-6931:X22': {'1': '00'}}
    if {name: source['connectors'][name] for name in expected} != expected:
        raise ValueError('page-18 X21/X22 source read changed')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory) / 'rail-terminals.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                        'kicadxml', '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        actual = {name: physical_pins(xml, name) for name in expected}
    mapped = {'012-6931:X21': {'1': 'p12'}, '012-6931:X22': {'1': '0'}}
    passed = actual == mapped
    return dict(format='dac-monitor-page18-vertical-rail-terminals-comparison-v1',
                qualification='source-labelled physical terminal representation in a supplemental audit-only KiCad sheet; connected vertical supply remains an ideal-rail equivalent',
                source_sha256=sha(SOURCE), source_pdf_sha256=sha(source_pdf),
                sheet_sha256=sha(SHEET), script_sha256=sha(__file__),
                source_pins=expected, exported_nets=actual,
                pins_checked=2, passed=passed, a1_full_page_qualified=False)


if __name__ == '__main__':
    pdf = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
    report = run(pdf)
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['pins_checked']} rail pins checked; passed={report['passed']}")
    raise SystemExit(0 if report['passed'] else 2)
