"""Compare the source-visible collector C27 branch to a fresh KiCad export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page4-c27-source-netlist.json'
TRANSCRIPTION = ROOT/'reference/k7222-11/horizontal-output-transcription.json'
SHEET = ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'
PARTS = ('C27', 'C30', 'V17', 'V18', 'T3')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def component_pins(xml):
    root = ET.parse(xml).getroot()
    ids = {f'012-6921:{part}' for part in PARTS}
    refs = {}
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id in ids:
            if source_id in refs:
                raise ValueError('duplicate collector-branch component')
            refs[source_id] = comp.get('ref')
    if set(refs) != ids:
        raise ValueError('collector-branch component missing from export')
    by_ref = {ref: source_id for source_id, ref in refs.items()}
    pins = {source_id: {} for source_id in ids}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            source_id = by_ref.get(node.get('ref'))
            if source_id:
                pin = node.get('pin')
                if pin in pins[source_id]:
                    raise ValueError('collector-branch pin occurs twice')
                pins[source_id][pin] = net.get('name').removeprefix('/')
    return pins


def compare(source, transcription, xml):
    if source.get('format') != 'dac-monitor-page4-c27-source-netlist-v1':
        raise ValueError('wrong C27 source reading')
    if source['source']['file'] != 'older.pdf' or source['source']['page'] != 4:
        raise ValueError('wrong page-4 source')
    expected = {
        'COLLECTOR': {'C27:top', 'V17:cathode', 'V18:collector', 'T3:X2:7'},
        '00': {'C27:bottom', 'V17:anode', 'V18:emitter'},
    }
    if {key: set(value) for key, value in source['scope']['nets'].items()} != expected:
        raise ValueError('source C27 branch changed')
    parts = {row['source_id']: row for row in transcription['components']}
    for name in PARTS:
        if f'012-6921:{name}' not in parts:
            raise ValueError('model collector-branch part missing')
    if parts['012-6921:C27']['nodes'] != ['h_hot', '0']:
        raise ValueError('C27 transcription changed')
    ports = transcription['ports']
    pins = component_pins(xml)
    p = {name: pins[f'012-6921:{name}'] for name in PARTS}
    collector = p['V18'].get('1')
    ground = p['V18'].get('3')
    t3_pin = str(ports.index('X2_7') + 1)
    checks = {
        'c27_two_distinct_terminals': set(p['C27']) == {'1', '2'} and len(set(p['C27'].values())) == 2,
        'c27_between_collector_and_return': set(p['C27'].values()) == {collector, ground},
        'v17_cathode_at_collector': p['V17'].get('2') == collector,
        'v17_anode_at_return': p['V17'].get('1') == ground,
        't3_x2_7_at_collector': p['T3'].get(t3_pin) == collector,
        'collector_and_return_distinct': collector is not None and ground is not None and collector != ground,
    }
    c30_nets = set(p['C30'].values())
    return {
        'format': 'dac-monitor-page4-c27-comparison-v1',
        'qualification': 'scoped C27/collector source branch agrees with model; C30 placement/population remains a conditional model choice, not source-confirmed',
        'source_sha256': sha(SOURCE),
        'source_pdf_sha256': source['source']['pdf_sha256'],
        'transcription_sha256': sha(TRANSCRIPTION),
        'sheet_sha256': sha(SHEET),
        'model_nets': {'collector': collector, 'return': ground,
                       'c27': sorted(p['C27'].values()),
                       'c30': sorted(c30_nets)},
        'checks': checks,
        'model_c30_parallel_to_c27': c30_nets == {collector, ground},
        'c30_source_placement_verified': False,
        'unresolved': source['unresolved'],
        'passed': all(checks.values()),
    }


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from recorded C27 reading')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'horizontal-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(SHEET)], check=True, capture_output=True, text=True)
        return compare(source, json.loads(TRANSCRIPTION.read_text()), xml)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{sum(report['checks'].values())}/{len(report['checks'])} C27 branch checks pass")
    if not report['passed']:
        raise SystemExit(1)
