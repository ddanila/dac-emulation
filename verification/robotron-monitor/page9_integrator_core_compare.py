"""Check the page-9 A2 core source nets against a fresh KiCad export."""
import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import steady_supply
import page9_integrator_crossing_compare as crossing

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page9-integrator-core-source-read.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-integrator.kicad_sch'
PREVIOUS_READ = ROOT / 'reference/k7222-11/page9-integrator-crossing-source-read.json'

PIN_INDEX = {
    'V12': {'A': 0, 'K': 1},
    'V13': {'upper_right': 0, 'base': 1, 'lower_right': 2},
    'V16': {'A': 0, 'K': 1},
    'V17': {'A': 0, 'K': 1},
    'C14': {'positive': 0, 'negative': 1},
    'C15': {'left': 0, 'right': 1},
    'R33': {'upper': 0, 'lower': 1},
    'R39': {'upper': 0, 'lower': 1},
    'R40': {'upper': 0, 'lower': 1},
    'R41': {'upper': 0, 'lower': 1},
    'R42': {'upper': 0, 'lower': 1},
    'R44': {'upper': 0, 'lower': 1},
    'A2': {'cs': 0, 'minus': 1, 'plus': 2, 'reference': 3, 'vm': 4,
           'output': 5, 'vc': 6, 'vp': 7, 'compensation': 8, 'limit': 9},
}
MODEL_NET = {
    'PULSE': 'vertical_pulse', 'A2_PLUS': 'ramp_noninv',
    'V13_BASE': 'retrace_base', 'A2_MINUS': 'ramp_inv',
    'A2_COMP': 'ramp_comp', 'RAMP_BIAS': 'ramp_bias',
    'REFERENCE': 'vertical_reference', 'RAW_OUTPUT': 'ramp_raw',
    'DIODE_MID': 'ramp_diode', 'RAMP_OUTPUT': 'vertical_ramp',
    'LIMIT': 'ramp_limit', '12P': 'p12', '00': '0',
}


def compare(source, components):
    if source.get('format') != 'dac-monitor-page9-integrator-core-source-read-v1':
        raise ValueError('page-9 A2 source read changed')
    if set(source['source_nets']) != set(MODEL_NET):
        raise ValueError('page-9 A2 source nets changed')
    by_id = {component['source_id']: component for component in components}
    checked = []
    seen = set()
    for source_net, terminals in source['source_nets'].items():
        if not terminals or len(set(terminals)) != len(terminals):
            raise ValueError('empty or duplicate source terminals')
        for terminal in terminals:
            part, pin = terminal.split(':', 1)
            if terminal in seen or pin not in PIN_INDEX.get(part, {}):
                raise ValueError('unknown or repeated source terminal: ' + terminal)
            seen.add(terminal)
            component = by_id.get('012-6931:' + part)
            if component is None or component['nodes'][PIN_INDEX[part][pin]] != MODEL_NET[source_net]:
                raise ValueError('source-to-KiCad mismatch at ' + terminal)
            checked.append({'terminal': terminal, 'source_net': source_net,
                            'model_net': MODEL_NET[source_net]})
    if len(checked) != 35 or {row['terminal'].split(':')[0] for row in checked} != set(PIN_INDEX):
        raise ValueError('page-9 A2 source coverage changed')
    previous_source = json.loads(PREVIOUS_READ.read_text())
    crossing.compare(previous_source, components)
    previous_terminals = {terminal for terminals in previous_source['source_nets'].values()
                          for terminal in terminals}
    source_terminals = {row['terminal'] for row in checked} | previous_terminals
    source_terminals.discard('A2:2')  # Same physical pin as A2:minus above.
    all_ids = set(PIN_INDEX) | {'R34', 'R35', 'C22'}
    model_slots = sum(len(by_id['012-6931:' + part]['nodes']) for part in all_ids)
    verified_slots = len(source_terminals - {'R35:wiper'})
    if (len(all_ids) != 16 or len(source_terminals) != 42 or
            'R35:wiper' not in source_terminals or verified_slots != 41 or model_slots != 41):
        raise ValueError('combined page-9 integrator coverage changed')
    return {
        'format': 'dac-monitor-page9-integrator-core-comparison-v1',
        'qualification': 'scoped electrical-net comparison using the exact MAA723 pin map; V13 C/E identity conflicts with its later arrow read, and full page 9 remains open',
        'source_read_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'crossing_source_read_sha256': hashlib.sha256(PREVIOUS_READ.read_bytes()).hexdigest(),
        'sheet_sha256': hashlib.sha256(SHEET.read_bytes()).hexdigest(),
        'terminals_checked': len(checked),
        'combined_components_touched': len(all_ids),
        'combined_physical_source_terminals_read': len(source_terminals),
        'combined_model_terminal_slots_verified': verified_slots,
        'integrator_model_terminal_slots_total': model_slots,
        'unverified_a2_model_slot_indices': [],
        'checked': checked,
        'mismatches': [],
        'semiconductor_lead_identity_mismatch': {
            'source_id': '012-6931:V13',
            'source_read': 'reference/k7222-11/page9-v13-arrow-source-read.json',
            'drawn_upper_right': 'emitter',
            'active_spice_upper_right': 'collector',
            'status': 'open; source-order candidate fails the vertical ramp stage test',
        },
        'remaining': source['remaining'],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as directory:
        assembly = steady_supply.assemble(Path(directory) / 'assembly')
    report = compare(json.loads(SOURCE.read_text()), assembly['components'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"page-9 A2 core: {report['terminals_checked']} scoped terminals match")


if __name__ == '__main__':
    main()
