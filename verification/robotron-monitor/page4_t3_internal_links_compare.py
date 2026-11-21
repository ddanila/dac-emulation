"""Check two page-4 T3 conductor links against the transcription and fresh KiCad export."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import page4_booster_compare as booster


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page4-t3-internal-links-source-read.json'
TRANSCRIPTION = booster.TRANSCRIPTION
SHEET = booster.SHEET
VIEW = ROOT.parents[1] / 'build/monitor/phase-a/sources/older-page4-t3-lower-600.png'
PAIRS = [('X2_10', 'X1_15'), ('X2_11', 'X1_13')]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, transcription, pins):
    if source['format'] != 'dac-monitor-page4-t3-internal-links-source-read-v1':
        raise ValueError('wrong T3 internal-links source read')
    if source['drawn_conductor_pairs'] != [list(pair) for pair in PAIRS]:
        raise ValueError('source conductor pairs changed')
    ports = transcription['ports']
    t3 = next(part for part in transcription['components']
              if part['source_id'] == '012-6921:T3')
    if len(ports) != len(t3['nodes']):
        raise ValueError('T3 port and node counts differ')
    model = dict(zip(ports, t3['nodes']))
    if transcription['port_nets']['X2_10'] != 'h_boost':
        raise ValueError('booster source anchor changed')
    if transcription['port_nets']['X2_11'] != 'h_lower13':
        raise ValueError('lower tap source anchor changed')
    exported = pins['T3']
    checks = {}
    for left, right in PAIRS:
        left_pin, right_pin = str(ports.index(left) + 1), str(ports.index(right) + 1)
        model_net = model[left]
        check_name = f'{left}_to_{right}'
        checks[check_name] = (
            model_net is not None and model_net == model[right]
            and model_net == transcription['port_nets'][left]
            and model_net == transcription['port_nets'][right]
            and exported.get(left_pin) == exported.get(right_pin) == model_net
        )
    return {
        'format': 'dac-monitor-page4-t3-internal-links-comparison-v1',
        'qualification': 'two source-visible T3 conductor links only; other internal winding connections and complete page-4 comparison remain open',
        'source_read_sha256': sha(SOURCE),
        'source_pdf_sha256': source['source']['pdf_sha256'],
        'source_view_sha256': source['source']['view_sha256'],
        'transcription_sha256': sha(TRANSCRIPTION),
        'sheet_sha256': sha(SHEET),
        'model_nets': {port: model[port] for pair in PAIRS for port in pair},
        'checks': checks,
        'passed': all(checks.values()),
        'unresolved': source['unresolved'],
    }


def run(source_pdf, source_view):
    source = json.loads(SOURCE.read_text())
    if source['source']['file'] != 'older.pdf' or source['source']['page'] != 4:
        raise ValueError('wrong source page')
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF changed')
    if sha(source_view) != source['source']['view_sha256']:
        raise ValueError('source view changed')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory) / 'horizontal-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(SHEET)], check=True, capture_output=True,
                       text=True)
        pins = booster.exported_pins(xml)
    return compare(source, json.loads(TRANSCRIPTION.read_text()), pins)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--source-view', type=Path, default=VIEW)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf, args.source_view)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{sum(result['checks'].values())}/{len(result['checks'])} T3 conductor links pass")
    if not result['passed']:
        raise SystemExit(1)
