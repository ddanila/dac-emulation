"""Bound one source-visible 20-port connected startup drive diagnostic."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

import steady_supply
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-page4-connected-drive-diagnostic.json'
sys.path.insert(0, str(ROOT / 'tests'))
from test_frames import capture  # Explicit synthetic diagnostic stimulus.


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def trace_rows(path):
    with Path(path).open('rb') as stream:
        header = b''
        while not header.endswith(b'Binary:\n'):
            line = stream.readline()
            if not line or len(header) > 1000000:
                raise ValueError('missing ngspice raw header')
            header += line
        description = header.decode()
        count = int(re.search(r'No. Variables:\s+(\d+)', description)[1])
        declared = int(re.search(r'No. Points:\s+(\d+)', description)[1])
        names = re.findall(r'^\s*\d+\s+(\S+)\s+\S+\s*$',
                           description.split('Variables:\n')[1].split('Binary:')[0], re.M)
        if len(names) != count or names[0] != 'time' or 'Flags: real' not in description:
            raise ValueError('unsupported ngspice raw vectors')
        unpack = struct.Struct('=' + str(count) + 'd')
        rows = []
        while data := stream.read(unpack.size):
            if len(data) != unpack.size:
                raise ValueError('truncated raw trace')
            values = unpack.unpack(data)
            if not all(math.isfinite(value) for value in values):
                raise ValueError('nonfinite raw sample')
            rows.append(dict(zip(names, values)))
    if len(rows) != declared or not rows:
        raise ValueError('raw point count differs from ngspice declaration')
    return rows


def prefix_observation(rows):
    first_duplicate = next((i for i in range(1, len(rows))
                            if rows[i]['time'] == rows[i - 1]['time']), len(rows))
    if any(rows[i]['time'] < rows[i - 1]['time'] for i in range(1, len(rows))):
        raise ValueError('time decreases in raw trace')
    duplicates = [i for i in range(1, len(rows))
                  if rows[i]['time'] == rows[i - 1]['time']]
    window = [row for row in rows[:first_duplicate] if row['time'] >= .015]
    if not window:
        raise ValueError('no 15 ms diagnostic prefix')
    def bounds(values):
        return [min(values), max(values)]
    drive = [row['v(h_hot)'] - row['v(h_return)'] for row in window]
    c21 = [row['v(h_boost)'] - row['v(p41)'] for row in window]
    return dict(raw_points=len(rows), duplicate_time_count=len(duplicates),
                maximum_same_time_voltage_or_current_step=max(
                    (max(abs(a[key] - b[key]) for key in a if key != 'time')
                     for a, b in ((rows[i], rows[i - 1]) for i in duplicates)),
                    default=0),
                strict_prefix_rows=first_duplicate,
                strict_prefix_last_time_s=rows[first_duplicate - 1]['time'],
                measured_window_s=[window[0]['time'], window[-1]['time']],
                eht_v=bounds([row['v(eht)'] for row in window]),
                hot_to_return_drive_v=bounds(drive),
                h_return_v=bounds([row['v(h_return)'] for row in window]),
                collector_to_ground_v=bounds([row['v(h_hot)'] for row in window]),
                c21_differential_v=bounds(c21),
                yoke_current_pp_a=(max(row['i(lhorizontal)'] for row in window) -
                                   min(row['i(lhorizontal)'] for row in window)))


def run(ngspice):
    binary = Path(ngspice).resolve()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        assembly = steady_supply.assemble(root / 'assembly',
                                          t3_interface='page4-visible-20-port')
        candidate = transformer_candidates.enumerate_candidates(
            assembly['magnetic_graph'])[0]
        selection = steady_supply.select(capture())
        deck, metadata = steady_supply.deck(
            assembly, selection, candidate, magnetic_backend='coupled',
            max_step_s=50e-9)
        if metadata['t3_interface'] != 'page4-visible-20-port':
            raise ValueError('wrong connected T3 interface')
        cases = []
        for stop_ms, save_start_ms in ((16, 15), (20, 19)):
            case_dir = root / f'{stop_ms}ms'
            case_dir.mkdir()
            lines = []
            for line in deck.splitlines():
                if line.startswith('.tran '):
                    line = f'.tran 50n {stop_ms}ms {save_start_ms}ms 50n'
                if line.startswith('.save '):
                    line = ('.save time v(eht) v(h_hot) v(h_return) v(h_boost) '
                            'v(p41) i(Lhorizontal) v(h_outputbase) '
                            'v(h_drivecol) v(h_sync) v(h_feedback)')
                lines.append(line)
            circuit = '\n'.join(lines) + '\n'
            (case_dir / 'run.cir').write_text(circuit)
            process = subprocess.run(
                [str(binary), '-b', '-r', 'trace.raw', '-o', 'solver.log', 'run.cir'],
                cwd=case_dir, capture_output=True, text=True, timeout=120)
            log = (case_dir / 'solver.log').read_text()
            status = 'complete' if process.returncode == 0 and 'aborted' not in log else 'aborted'
            case = dict(stop_ms=stop_ms, saved_from_ms=save_start_ms,
                        status=status, returncode=process.returncode,
                        deck_sha256=hashlib.sha256(circuit.encode()).hexdigest())
            if status == 'complete':
                case['trace'] = prefix_observation(trace_rows(case_dir / 'trace.raw'))
            else:
                match = re.search(r'Timestep too small; time = ([\d.e+-]+), '
                                  r'timestep = ([\d.e+-]+): trouble with node "([^"]+)"', log)
                if match is None:
                    raise ValueError('connected run failed without a classified solver error')
                case['solver_failure'] = dict(time_s=float(match[1]),
                                              step_s=float(match[2]), node=match[3])
            cases.append(case)
    inputs = (ROOT / 'steady_supply.py', ROOT / 'transformer_candidates.py',
              ROOT / 'tests/test_frames.py',
              ROOT / 'circuits/k7222-11-horizontal-output-page4.kicad_sch',
              REF / 't3-page4-visible-graph.json',
              REF / 't3-page4-provisional-parameters.json',
              REF / 'page4-t3-visible-wrapper-comparison.json', Path(__file__))
    return dict(format='dac-monitor-t3-page4-connected-drive-diagnostic-v1',
                qualification='synthetic native-pattern connected startup diagnostic, not a periodic or source-qualified T3 design point; strict raw parser rejects repeated timestamps in the 16 ms trace',
                input_sha256={str(path.relative_to(ROOT)): sha(path) for path in inputs},
                ngspice_sha256=sha(binary),
                interface=metadata['t3_interface'],
                magnetic_backend=metadata['magnetic_backend'],
                contrast_topology=metadata['contrast_topology'],
                period_s=metadata['period_s'],
                source_kind=metadata['source_kind'],
                cases=cases,
                limitations=['The 16 ms prefix is startup, and its repeated timestamps prevent strict trace acceptance.',
                             'The 20 ms run fails in V4/D206; no complete field or settled X2:4 waveform is available.',
                             'HV cold end and installed 20-port winding parameters remain unqualified.'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    for case in report['cases']:
        print(case['stop_ms'], case['status'],
              case.get('trace', case.get('solver_failure')))
