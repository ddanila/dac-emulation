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
VISIBLE_SOURCE = REF / 'page4-t3-terminal-identity-source-read.json'
VISIBLE_COMPARE = REF / 'page4-t3-visible-wrapper-comparison.json'
DESIGN = REF / 'design-point.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    drive = json.loads(DRIVE.read_text())
    return_read = json.loads(RETURN_SOURCE.read_text())
    return_compare = json.loads(RETURN_COMPARE.read_text())
    assembly = json.loads(TRANSCRIPTION.read_text())
    visible_source = json.loads(VISIBLE_SOURCE.read_text())
    visible_compare = json.loads(VISIBLE_COMPARE.read_text())
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
    if (visible_source['source']['pdf_sha256'] != drive['source_pdf_sha256'] or
            visible_compare['source_sha256'] != sha(VISIBLE_SOURCE) or
            visible_compare['historical_sheet_sha256'] != return_compare['sheet_sha256'] or
            not visible_compare['passed'] or
            not all(visible_compare['checks'].values())):
        raise ValueError('source-visible 20-port T3 interface changed')
    labels = visible_source['visible_labels']
    if (labels['v21_anode_pad'] != 'X3:1' or labels['v21_cathode_pad'] != 'X3:2' or
            ['X1:2', 'X2:3'] not in visible_source['drawn_conductor_pairs']):
        raise ValueError('source-visible V21 or upper return changed')
    ports = assembly['port_nets']
    if ports['X2_7'] != 'h_hot' or ports['X2_4'] != 'h_return':
        raise ValueError('candidate assembly drive nets changed')
    corrected = visible_compare['exported_nodes']
    if (corrected['X2_7'] != ports['X2_7'] or
            corrected['X2_4'] != ports['X2_4'] or
            corrected['X3_1'] != visible_compare['v21_pins']['1'] or
            visible_compare['v21_pins']['2'] != 'eht' or
            corrected['X1_2'] != corrected['X2_3']):
        raise ValueError('corrected T3 drive or V21 nets differ from source read')
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
    if (ratio['equation'] != 'EHT / collector_flyback_peak' or
            not design['t3_terminal_identity']['active_19_port_model_source_contradicted'] or
            design['t3_terminal_identity']['v21_anode_pad'] != 'X3:1'):
        raise ValueError('design-point collector proxy changed')
    ratio_bounds = ratio['ratio_if_boost_case_is_correct']
    historical_scale = design['conditional_t3_hv_turn_scale']
    if historical_scale['valid_for_current_20_port_graph'] is not False:
        raise ValueError('historical turn scale was promoted without a new source argument')
    turn_bounds = historical_scale['candidate_hv_turns_if_current_drive_scale_and_boost_case_hold']
    return dict(
        format='dac-monitor-t3-drive-voltage-audit-v3',
        qualification='source-read drive pair and 20-port V21/upper interface with scoped X2:4/C31/C32-to-H2 return; no full page-4 netlist, HV cold-end mapping, differential pulse or T3 ratio',
        source_pdf_sha256=drive['source_pdf_sha256'],
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (DRIVE, RETURN_SOURCE, RETURN_COMPARE,
                                    TRANSCRIPTION, VISIBLE_SOURCE, VISIBLE_COMPARE,
                                    DESIGN, Path(__file__))},
        source_read_drive_terminals=source['drive_winding_endpoints'],
        source_read_v21_pads={'anode': labels['v21_anode_pad'],
                              'cathode': labels['v21_cathode_pad']},
        source_read_return_branch=return_read['scope']['nets'],
        candidate_assembly_nets={'X2:7': corrected['X2_7'],
                                 'X2:4': corrected['X2_4'],
                                 'X3:1': corrected['X3_1'],
                                 'X1:2': corrected['X1_2'],
                                 'X2:3': corrected['X2_3'],
                                 'H2/X5:5': return_compare['model_nets']['x5_pin5']},
        candidate_return_branches=return_parts,
        existing_design_point_equation=ratio['equation'],
        required_drive_voltage='V(X2:7)-V(X2:4) = V(h_hot)-V(h_return) in the source-visible 20-port candidate',
        required_hv_voltage='V(X3:1)-V(HV cold end); the cold-end terminal and its potential are not source-qualified',
        conclusion=(f'EHT divided by the ideal collector-to-ground peak remains only a {ratio_bounds["minimum"]:.2f}-{ratio_bounds["maximum"]:.2f} conditional voltage proxy, not the T3 HV-to-drive turns ratio. V21 anode is X3:1, not X1:1. X2:4 returns through C31/C32 to H2 at X5:5, but the H2/X2:4 flyback waveforms and the HV cold end are not source-bounded. The historical {turn_bounds["minimum"]}-{turn_bounds["maximum"]}-turn scale from the 19-port graph cannot qualify the 20-port winding.'),
        next='Bound the HV cold-end mapping and H2-coupled X2:4 waveform, then the differential X2:7-to-X2:4 flyback pulse and settled rectified loading before deriving an HV/drive ratio; retain the older turn sweep as historical sensitivity only.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(report['required_drive_voltage'])
