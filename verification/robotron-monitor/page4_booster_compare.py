"""Compare the page-4 booster tap read with a fresh horizontal-board export."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page4-booster-source-netlist.json'
TRANSCRIPTION = ROOT / 'reference/k7222-11/horizontal-output-transcription.json'
SHEET = ROOT / 'circuits/k7222-11-horizontal-output.kicad_sch'
PARTS = ('C21', 'C26', 'V16', 'T3')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def exported_pins(xml):
    root = ET.parse(xml).getroot()
    ids = {f'012-6921:{name}' for name in PARTS}
    refs = {}
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id in ids:
            if source_id in refs:
                raise ValueError(f'duplicate {source_id}')
            refs[source_id] = comp.get('ref')
    if set(refs) != ids:
        raise ValueError(f'missing source IDs: {sorted(ids - set(refs))}')
    by_ref = {ref: source_id for source_id, ref in refs.items()}
    pins = {source_id: {} for source_id in ids}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            source_id = by_ref.get(node.get('ref'))
            if source_id:
                pin = node.get('pin')
                if pin in pins[source_id]:
                    raise ValueError(f'duplicate pin {source_id}:{pin}')
                pins[source_id][pin] = net.get('name').removeprefix('/')
    return {name: pins[f'012-6921:{name}'] for name in PARTS}


def compare(source, transcription, xml):
    if source['format'] != 'dac-monitor-page4-booster-source-netlist-v1':
        raise ValueError('wrong booster source read')
    if source['source']['file'] != 'older.pdf' or source['source']['page'] != 4:
        raise ValueError('wrong page-4 source')
    expected = {
        '41P_FEED': {'C21:feed', 'C26:feed', 'V16:anode'},
        'RECTIFIED_TAP': {'C26:tap', 'V16:cathode', 'T3:X2:13'},
        'BOOST_CAPACITOR': {'C21:tap', 'T3:X2:10'},
    }
    if {key: set(value) for key, value in source['scope']['nets'].items()} != expected:
        raise ValueError('source booster branch changed')
    parts = {row['source_id']: row for row in transcription['components']}
    if parts['012-6921:C21']['nodes'] != ['h_feed', 'h_boost']:
        raise ValueError('C21 transcription changed')
    if parts['012-6921:C26']['nodes'] != ['h_feed', 'h_boosttap']:
        raise ValueError('C26 transcription changed')
    if parts['012-6921:V16']['nodes'] != ['h_feed', 'h_boosttap']:
        raise ValueError('V16 transcription changed')
    pins = exported_pins(xml)
    t3 = pins['T3']
    ports = transcription['ports']
    tap13 = t3.get(str(ports.index('X2_13') + 1))
    tap10 = t3.get(str(ports.index('X2_10') + 1))
    feed = pins['C21'].get('1')
    rectified = pins['V16'].get('2')
    boost = pins['C21'].get('2')
    checks = {
        'feed_shared': feed is not None and feed == pins['C26'].get('1') == pins['V16'].get('1'),
        'v16_c26_parallel': rectified is not None and rectified == pins['C26'].get('2'),
        'v16_c26_to_x2_13': rectified is not None and rectified == tap13,
        'c21_to_x2_10': boost is not None and boost == tap10,
        'three_distinct_nets': len({feed, rectified, boost}) == 3 and None not in {feed, rectified, boost},
    }
    return {
        'format': 'dac-monitor-page4-booster-comparison-v1',
        'qualification': 'scoped external booster wiring only; internal T3 graph and complete page-4 comparison remain open',
        'source_sha256': sha(SOURCE),
        'source_pdf_sha256': source['source']['pdf_sha256'],
        'transcription_sha256': sha(TRANSCRIPTION),
        'sheet_sha256': sha(SHEET),
        'model_nets': {'feed': feed, 'v16_c26_output': rectified, 'c21_output': boost,
                       't3_x2_13': tap13, 't3_x2_10': tap10},
        'checks': checks,
        'passed': all(checks.values()),
        'unresolved': source['unresolved'],
    }


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from recorded page-4 read')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory) / 'horizontal-output.xml'
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
    print(f"{sum(report['checks'].values())}/{len(report['checks'])} booster wiring checks pass")
    if not report['passed']:
        raise SystemExit(1)
