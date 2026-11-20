"""Check the voltage reference needed to derive a T3 HV/drive ratio."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
DRIVE = REF / 't3-drive-polarity-source-read.json'
TRANSCRIPTION = REF / 'horizontal-output-transcription.json'
DESIGN = REF / 'design-point.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    drive = json.loads(DRIVE.read_text())
    assembly = json.loads(TRANSCRIPTION.read_text())
    design = json.loads(DESIGN.read_text())
    source = drive['source_edges']
    if source['drive_winding_endpoints'] != ['X2:7', 'X2:4']:
        raise ValueError('source-read drive endpoints changed')
    if source['output_transistor_collector'] != dict(part='V18', terminal='C',
                                                     t3_terminal='X2:7'):
        raise ValueError('source-read collector connection changed')
    ports = assembly['port_nets']
    if ports['X2_7'] != 'h_hot' or ports['X2_4'] != 'h_return':
        raise ValueError('candidate assembly drive nets changed')
    return_parts = [dict(source_id=row['source_id'], nodes=row['nodes'],
                         value=row['value'])
                    for row in assembly['components']
                    if 'h_return' in row['nodes'] and row['source_id'] != '012-6921:T3']
    if {row['source_id'] for row in return_parts} != {'012-6921:C31', '012-6921:C32'}:
        raise ValueError('candidate assembly return branches changed')
    ratio = design['high_voltage_ratio']
    if ratio['equation'] != 'EHT / collector_flyback_peak':
        raise ValueError('design-point collector proxy changed')
    return dict(
        format='dac-monitor-t3-drive-voltage-audit-v1',
        qualification='source-read drive terminals plus unvalidated assembly-candidate return; no measured differential pulse or T3 ratio',
        source_pdf_sha256=drive['source_pdf_sha256'],
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (DRIVE, TRANSCRIPTION, DESIGN, Path(__file__))},
        source_read_drive_terminals=source['drive_winding_endpoints'],
        candidate_assembly_nets={'X2:7': ports['X2_7'], 'X2:4': ports['X2_4']},
        candidate_return_branches=return_parts,
        existing_design_point_equation=ratio['equation'],
        required_drive_voltage='V(X2:7)-V(X2:4) = V(h_hot)-V(h_return) in the assembly candidate',
        conclusion='EHT divided by collector-to-ground peak is a conditional voltage proxy, not the T3 HV-to-drive turns ratio. X2:4 is a distinct candidate return node and its flyback waveform is not source-bounded. Neither the 28.24-35.94 collector proxy nor the 1808-2300 turn scale may qualify T3 turns.',
        next='Source-qualify X2:4 return and obtain a bounded differential X2:7-to-X2:4 flyback pulse before using EHT to derive an HV/drive ratio; retain the existing turn sweep as an isolated sensitivity only.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['required_drive_voltage'])
