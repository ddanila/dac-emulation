"""Evaluate the reviewed TI LS00 typical DC curves with the schematic clock pullup.

A local comparison at 5 V, not a DL000 model or IBIS package import. No vendor
curve data are emitted. Current is positive into the output pin; the pullup
voltage coordinate is Vcc minus Vout, per the IBIS specification.
"""
import argparse
import bisect
import hashlib
import json
import math
from pathlib import Path
import re

from circuit import load
from clock_output_probe import wiring

SOURCE_SHA = '78985e8a49cd8aaf8679e31e9f2375c4144f298a54bfffcfb1da7b61d262854b'


def tables(text):
    model = section = None
    found = {}
    for raw in text.splitlines():
        line = raw.partition('|')[0].strip()
        if not line:
            continue
        match = re.match(r'^\[([^]]+)\]\s*(.*)$', line)
        if match:
            section = match[1].lower()
            if section == 'model':
                model = match[2].strip()
            if model == 'ls00_OUT' and section in ('pullup', 'pulldown'):
                if section in found:
                    raise ValueError('Duplicate output table')
                found[section] = []
            continue
        if model == 'ls00_OUT' and section in ('pullup', 'pulldown'):
            row = list(map(float, line.split()))
            if len(row) != 4 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid output table row')
            if found[section] and row[0] <= found[section][-1][0]:
                raise ValueError('Table voltage must increase strictly')
            found[section].append(row)
    if set(found) != {'pullup', 'pulldown'} or any(len(t) < 2 for t in found.values()):
        raise ValueError('Missing output curves')
    return found


def interpolate(points, voltage):
    if not points[0][0] <= voltage <= points[-1][0]:
        raise ValueError('Curve extrapolation is forbidden')
    i = min(bisect.bisect_right([p[0] for p in points], voltage) - 1, len(points) - 2)
    (x0, y0), (x1, y1) = points[i:i + 2]
    return y0 + (y1 - y0) * (voltage - x0) / (x1 - x0)


def equilibrium(points, supply, resistance):
    if not math.isfinite(supply) or not math.isfinite(resistance) or supply <= 0 or resistance <= 0:
        raise ValueError('Positive finite supply and resistance required')
    if len(points) < 2 or any(not all(map(math.isfinite, p)) for p in points):
        raise ValueError('Invalid curve')
    if any(a[0] >= b[0] for a, b in zip(points, points[1:])):
        raise ValueError('Curve voltage must increase strictly')
    knots = [0] + [p[0] for p in points if 0 < p[0] < supply] + [supply]
    residuals = [interpolate(points, v) + (v - supply) / resistance for v in knots]
    roots = {v for v, current in zip(knots, residuals) if current == 0}
    for a, b, ia, ib in zip(knots, knots[1:], residuals, residuals[1:]):
        if ia == ib == 0:
            raise ValueError('Indeterminate equilibrium interval')
        if ia * ib < 0:
            roots.add(a - ia * (b - a) / (ib - ia))
    if len(roots) != 1:
        raise ValueError('Expected one in-range DC equilibrium')
    voltage = roots.pop()
    residual = interpolate(points, voltage) + (voltage - supply) / resistance
    if abs(residual) > 1e-12:
        raise ValueError('DC current balance failed')
    return {'outputVolts': voltage, 'pullupAmps': (supply - voltage) / resistance,
            'kclResidualAmps': residual}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ibis', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw = args.ibis.read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA:
        raise ValueError('Unreviewed IBIS source; review before using its tables')
    curves = tables(raw.decode('latin-1'))
    components, connectivity_sha = load()
    wiring(components, 0)  # Independently reject a changed schematic clock path.
    resistance = float(components['R10.3']['type'])
    cases = {}
    for state, table in [('high', 'pullup'), ('low', 'pulldown')]:
        points = sorted((5 - row[0] if state == 'high' else row[0], row[1]) for row in curves[table])
        cases[state] = equilibrium(points, 5, resistance)
    report = {'qualified': False, 'sourceSha256': SOURCE_SHA,
              'sourceUrl': 'https://www.ti.com/lit/ibs/SDLM003',
              'conventionReference': 'https://www.ibis.org/ver6.1/ver6_1.pdf',
              'connectivitySha256': connectivity_sha, 'pullupReference': 'R10.3',
              'pullupOhms': resistance, 'supplyVolts': 5, 'column': 'typical',
              'cases': cases,
              'scope': 'Static current balance using explicit ls00_OUT curves, ideal closed BR1 and no CPU leakage. Package pin maps are not imported. No added clamp currents: this reviewed non-tristate output model has no separate clamp tables.',
              'boundary': 'TI comparison device only. Not DL000 calibration, switching, oscillator startup, temperature or supply-corner qualification. No scaling of 5 V curves into undervoltage startup.',
              'sources': {name: hashlib.sha256((Path(__file__).parent / name).read_bytes()).hexdigest()
                          for name in ('ls00_ibis_loadline.py', 'circuit.py', 'clock_output_probe.py')}}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
