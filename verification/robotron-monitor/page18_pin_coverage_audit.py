"""Account for every page-18 source-labelled endpoint across existing audits."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
FILES = {
    'source': 'page18-interconnect-transcription.json',
    'cables': 'page18-board-cable-pin-comparison.json',
    'input': 'page18-external-input-comparison.json',
    'panel': 'page18-panel-topology-comparison.json',
    'yoke': 'page18-yoke-pin-comparison.json',
    'neck_source': 'page16-neck-source-netlist.json',
    'neck_compare': 'page16-neck-comparison.json',
    'rail_terminals': 'page18-vertical-rail-terminals-comparison.json',
}
OUTPUT = REF / 'page18-pin-coverage-audit.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    reports = {name: json.loads((REF / file).read_text()) for name, file in FILES.items()}
    source = reports['source']['connectors']
    expected = {(connector, pin) for connector, pins in source.items() for pin in pins}
    proof = {}

    def record(connector, pin, source_name):
        if (connector, pin) not in expected:
            raise ValueError(f'comparison mentions non-source pin {connector}:{pin}')
        proof.setdefault((connector, pin), []).append(source_name)

    cables = reports['cables']
    if not cables['passed'] or cables['pin_misses'] or cables['extra_kicad_connector_pins']:
        raise ValueError('page-18 cable comparison no longer passes')
    if len(cables['cable_pairs']) != 18:
        raise ValueError('source cable coverage changed')
    for row in cables['cable_pairs']:
        for side in ('from', 'to'):
            connector, pin = row[side + '_connector'], row[side + '_pin']
            if source[connector][pin] != row['source_signal'] or row[side + '_export_net'] != row['model_net']:
                raise ValueError('cable pin differs from source or export')
            record(connector, pin, 'cables')

    input_report = reports['input']
    if not input_report['physical_x9_present'] or input_report['physical_pins_checked'] != 5:
        raise ValueError('X9 physical pin check changed')
    if {row['pin'] for row in input_report['signal_rows']} | set(input_report['return_pins']) != set(source['012-6921:X9']):
        raise ValueError('X9 source pin set changed')
    for pin in source['012-6921:X9']:
        record('012-6921:X9', pin, 'input')

    panel = reports['panel']
    if (panel['physical_connector_pins_checked'] != 6 or panel['physical_connector_pin_misses']
            or panel['mismatches'] or not panel['brightness_topology_matches']
            or not panel['contrast_topology_matches']):
        raise ValueError('panel pin/topology check changed')
    for connector in ('012-6921:X1', 'panel:R1', 'panel:R2'):
        for pin in source[connector]:
            if connector.startswith('panel:'):
                key = 'source_r' + connector[-1] + '_terminals'
                if panel[key][pin] != source[connector][pin]:
                    raise ValueError('panel source terminal changed')
            record(connector, pin, 'panel')

    yoke = reports['yoke']
    if not yoke['passed'] or yoke['pin_misses'] or yoke['winding_misses']:
        raise ValueError('yoke pin comparison changed')
    for row in yoke['board_connector']:
        if row['source_signal'] != source['012-6931:X2'][row['pin']]:
            raise ValueError('vertical yoke connector label changed')
        record('012-6931:X2', row['pin'], 'yoke')
    for row in yoke['yoke_terminals']:
        if row['source_signal'] != source['yoke'][row['yoke_pin']]:
            raise ValueError('yoke terminal label changed')
        record('yoke', row['yoke_pin'], 'yoke')

    neck = reports['neck_compare']
    if not neck['passed'] or neck['matched_connector_pins'] != neck['source_connector_pins']:
        raise ValueError('page-16 neck source comparison changed')
    neck_pins = {pin.split(':', 1)[1] for pins in reports['neck_source']['nets'].values()
                 for pin in pins if pin.startswith('X2:')}
    if neck_pins != set(source['012-6891:X2']):
        raise ValueError('page-16 neck X2 pin set differs from page 18')
    for pin in neck_pins:
        record('012-6891:X2', pin, 'neck')

    rails = reports['rail_terminals']
    if not rails['passed'] or rails['pins_checked'] != 2:
        raise ValueError('X21/X22 source terminal export changed')
    for connector, pins in rails['source_pins'].items():
        if pins != source[connector] or rails['exported_nets'][connector] != {
                pin: {'12P': 'p12', '00': '0'}[signal]
                for pin, signal in pins.items()}:
            raise ValueError('X21/X22 source or exported net mismatch')
        for pin in pins:
            record(connector, pin, 'rail_terminals')

    missing = sorted(expected - set(proof))
    unexpected = sorted(set(proof) - expected)
    if unexpected:
        raise ValueError('coverage outside source pin inventory')
    return dict(format='dac-monitor-page18-pin-coverage-audit-v1',
                qualification='coverage accounting over existing partial comparisons; not a fresh independent netlist or complete page-18 functional signoff',
                input_sha256={file: sha(REF / file) for file in FILES.values()},
                script_sha256=sha(Path(__file__)),
                source_endpoint_count=len(expected), covered_endpoint_count=len(proof),
                proof_counts={name: sum(name in proofs for proofs in proof.values())
                              for name in ('cables', 'input', 'panel', 'yoke', 'neck', 'rail_terminals')},
                uncovered=[dict(connector=c, pin=p, source_signal=source[c][p]) for c, p in missing],
                functional_model_scope_gaps=cables['functional_model_scope_gaps'],
                physical_endpoint_comparison_complete=not missing,
                a1_page18_complete=False,
                audit_passed=len(expected) == 70 and len(proof) == 70 and not missing)


if __name__ == '__main__':
    report = run()
    OUTPUT.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['covered_endpoint_count']}/{report['source_endpoint_count']} source endpoints covered; audit passed={report['audit_passed']}")
    raise SystemExit(0 if report['audit_passed'] else 2)
