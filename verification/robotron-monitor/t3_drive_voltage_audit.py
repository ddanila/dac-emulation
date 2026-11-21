"""Check the voltage reference needed to derive a T3 HV/drive ratio."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
DRIVE = REF / 't3-drive-polarity-source-read.json'
RETURN_SOURCE = REF / 'page4-t3-x2-return-source-netlist.json'
RETURN_COMPARE = REF / 'page4-t3-x2-return-comparison.json'
TRANSCRIPTION = REF / 'horizontal-output-transcription.json'
DESIGN = REF / 'design-point.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    drive = json.loads(DRIVE.read_text())
    return_read = json.loads(RETURN_SOURCE.read_text())
    return_compare = json.loads(RETURN_COMPARE.read_text())
    assembly = json.loads(TRANSCRIPTION.read_text())
    design = json.loads(DESIGN.read_text())
    source = drive['source_edges']
    if source['drive_winding_endpoints'] != ['X2:7', 'X2:4']:
        raise ValueError('source-read drive endpoints changed')
    if source['output_transistor_collector'] != dict(part='V18', terminal='C',
                                                     t3_terminal='X2:7'):
        raise ValueError('source-read collector connection changed')
    if (return_read['source']['pdf_sha256'] != drive['source_pdf_sha256'] or
            return_compare['source_sha256'] != sha(RETURN_SOURCE) or
            not return_compare['passed'] or
            not all(return_compare['checks'].values())):
        raise ValueError('source-read X2:4 external return changed')
    ports = assembly['port_nets']
    if ports['X2_7'] != 'h_hot' or ports['X2_4'] != 'h_return':
        raise ValueError('candidate assembly drive nets changed')
    return_parts = [dict(source_id=row['source_id'], nodes=row['nodes'],
                         value=row['value'])
                    for row in assembly['components']
                    if 'h_return' in row['nodes'] and row['source_id'] != '012-6921:T3']
    if {row['source_id'] for row in return_parts} != {'012-6921:C31', '012-6921:C32'}:
        raise ValueError('candidate assembly return branches changed')
    if (return_compare['model_nets']['x5_pin5'] != 'hy2' or
            any(row['nodes'] != ['hy2', 'h_return'] for row in return_parts)):
        raise ValueError('H2 capacitor return differs from candidate assembly')
    ratio = design['high_voltage_ratio']
    if ratio['equation'] != 'EHT / collector_flyback_peak':
        raise ValueError('design-point collector proxy changed')
    ratio_bounds = ratio['ratio_if_boost_case_is_correct']
    turn_bounds = design['conditional_t3_hv_turn_scale'][
        'candidate_hv_turns_if_current_drive_scale_and_boost_case_hold']
    return dict(
        format='dac-monitor-t3-drive-voltage-audit-v2',
        qualification='source-read drive pair and scoped X2:4/C31/C32-to-H2 external return; no full page-4 netlist, measured differential pulse or T3 ratio',
        source_pdf_sha256=drive['source_pdf_sha256'],
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (DRIVE, RETURN_SOURCE, RETURN_COMPARE,
                                    TRANSCRIPTION, DESIGN, Path(__file__))},
        source_read_drive_terminals=source['drive_winding_endpoints'],
        source_read_return_branch=return_read['scope']['nets'],
        candidate_assembly_nets={'X2:7': ports['X2_7'], 'X2:4': ports['X2_4'],
                                 'H2/X5:5': return_compare['model_nets']['x5_pin5']},
        candidate_return_branches=return_parts,
        existing_design_point_equation=ratio['equation'],
        required_drive_voltage='V(X2:7)-V(X2:4) = V(h_hot)-V(h_return) in the assembly candidate',
        conclusion=(f'EHT divided by collector-to-ground peak is a conditional voltage proxy, not the T3 HV-to-drive turns ratio. X2:4 returns through C31/C32 to H2 at X5:5, but the H2 and X2:4 flyback waveforms are not source-bounded. Neither the corrected {ratio_bounds["minimum"]:.2f}-{ratio_bounds["maximum"]:.2f} collector proxy nor the {turn_bounds["minimum"]}-{turn_bounds["maximum"]} turn scale may qualify T3 turns.'),
        next='Bound the H2-coupled X2:4 waveform and differential X2:7-to-X2:4 flyback pulse before using EHT to derive an HV/drive ratio; retain the existing turn sweep as an isolated sensitivity only.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['required_drive_voltage'])
