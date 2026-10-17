#!/usr/bin/env python3
"""Inventory physical data-bus endpoints and applicable reference electrical limits."""
import argparse
import hashlib
import json
from pathlib import Path

from circuit import load

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DATA_PINS = {
    'A5': ('U880', 'bidirectional', (14, 15, 12, 8, 7, 9, 10, 13)),
    'A8': ('U556_2716', 'tristate_output', (9, 10, 11, 13, 14, 15, 16, 17)),
    'A4': ('I8282', 'tristate_output', (19, 18, 17, 16, 15, 14, 13, 12)),
}


def inventory(components, limits):
    # These are chip package pin functions, not a second wiring source.
    # All attachments and net identities are read from normalized KiCad data.
    for ref, (kind, _, pins) in DATA_PINS.items():
        if components[ref]['type'] != kind:
            raise ValueError('Unsupported bus device: ' + ref)
        for bit, pin in enumerate(pins):
            if components[ref]['pins'][str(pin)] != f'/D{bit}':
                raise ValueError(f'Unexpected data pin/net mapping: {ref}:{pin}')
    buses = []
    for bit in range(8):
        net = f'/D{bit}'
        endpoints = []
        for ref, component in sorted(components.items()):
            for pin, attached in sorted(component['pins'].items()):
                if attached != net:
                    continue
                kind = component['type']
                if ref in DATA_PINS and int(pin) == DATA_PINS[ref][2][bit]:
                    role = DATA_PINS[ref][1]
                elif kind == '7406' and int(pin) in (1, 3, 5, 9, 11, 13):
                    role = 'input'
                else:
                    raise ValueError(f'Unclassified bus attachment: {ref}:{pin} ({kind}) on {net}')
                profile = limits['profiles'][kind]
                cap = 'inputCapacitance' if role == 'input' else 'outputCapacitance'
                endpoints.append({'reference': ref, 'pin': pin, 'role': role,
                                  'profile': kind, 'source': profile['source'],
                                  'capacitanceReference': profile[cap]})
        buses.append({'net': net, 'endpoints': endpoints,
                      'externalPassiveAttachments': [],
                      'releasedVoltageQualified': False})
    return {'completed': True, 'qualified': False, 'buses': buses,
            'limitations': [
                'No external data-bus pullup appears in the normalized schematic; digital tri1 is a behavioral assumption.',
                'Published test-point limits are not complete voltage/current curves or calibrated clone models.',
                'Released voltage requires leakage, input bias, capacitance and initial-state modeling; no floating-bit value is proved.',
                'Contention currents, supply coupling and transient pin timing remain unqualified.',
            ]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/bus-inventory')
    args = parser.parse_args()
    components, connectivity_sha = load()
    limits = json.loads((HERE / 'bus_limits.json').read_text())
    report = inventory(components, limits)
    report.update(connectivitySha256=connectivity_sha,
                  sources={name: hashlib.sha256((HERE / name).read_bytes()).hexdigest()
                           for name in ('bus_inventory.py', 'bus_limits.json', 'circuit.py')},
                  referenceLimits=limits)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
    print(args.out / 'report.json')


if __name__ == '__main__':
    main()
