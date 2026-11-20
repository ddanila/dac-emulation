"""Locate the source of the modeled page-3/4 IS high interval.

The zero-capacitance case is a diagnostic intervention on neck diode V2:4,
not a proposed replacement for the printed part. The other two cases use
the existing exploratory junction-capacitance bounds.
"""
import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import tempfile

import signal_path


ROOT = Path(__file__).resolve().parent
SEAM = ROOT/'reference/k7222-11/page3-4-intens-seam-source-read.json'
NECK_PROFILE = ROOT/'profiles/k7222-11-neck.json'
DURATION = .0002
STEP = 5e-9
SETTLE = .5e-6
D4_LINE = 'D4 intens brightness 1AD50_BOUND'
ALTERNATE_MODEL = '.model 1AD50_D4_CJO D(IS={d_is} N={d_n} RS={d_rs} CJO={capacitance} TT={d_tt} BV={d_bv} IBV={d_ibv})'


def read_samples(path):
    with path.open() as stream:
        columns = next(stream).split()
        expected = {'time', 'receiver_intens', 'cathode', 'monitor_video', 'monitor_intens'}
        if not expected.issubset(columns):
            raise ValueError('input/neck trace lacks IS or stimulus probes')
        return columns, [list(map(float, line.split())) for line in stream if line.split()]


def stable_states(path, events, clock_hz):
    columns, rows = read_samples(path)
    times = [event[0]/clock_hz for event in events]
    groups = {}
    for row in rows:
        time = row[0]
        index = bisect_right(times, time)-1
        if index < 0 or time > DURATION or time-times[index] < SETTLE:
            continue
        end = min(times[index+1] if index+1 < len(times) else DURATION, DURATION)
        if end-time < SETTLE:
            continue
        state = (events[index][1], events[index][3])
        groups.setdefault(state, []).append(row)
    result = []
    for (video, intensity), selected in sorted(groups.items()):
        values = [row[columns.index('receiver_intens')] for row in selected]
        cathode = [row[columns.index('cathode')] for row in selected]
        result.append({'logic_video': video, 'logic_intensity': intensity,
                       'sample_count': len(values),
                       'is_median_v': statistics.median(values),
                       'is_minimum_v': min(values), 'is_maximum_v': max(values),
                       'cathode_median_v': statistics.median(cathode)})
    if {(row['logic_video'], row['logic_intensity']) for row in result} != {
            (0, 1), (1, 0), (1, 1)}:
        raise ValueError('highlight capture does not expose required stable logic states')
    return result


def replace_source(deck, name, value):
    lines = deck.splitlines()
    matches = [index for index, line in enumerate(lines)
               if line.startswith(f'Vlogic_{name} ')]
    if len(matches) != 1:
        raise ValueError('logic source missing from input/neck deck')
    lines[matches[0]] = f'Vlogic_{name} logic_{name} 0 {value}'
    return '\n'.join(lines)+'\n'


def solve(deck, folder):
    folder.mkdir()
    (folder/'run.cir').write_text(deck)
    process = subprocess.run(['ngspice', '-b', 'run.cir'], cwd=folder,
                             capture_output=True, text=True)
    log = process.stdout+process.stderr
    if (process.returncode or 'Error:' in log or 'Timestep too small' in log or
            not (folder/'samples.txt').is_file()):
        raise RuntimeError('IS diagnostic solve failed: '+log[-500:])
    return folder/'samples.txt'


def run(capture_path):
    capture_path = Path(capture_path)
    seam = json.loads(SEAM.read_text())['model_correction']
    if (seam['V5_collector_and_V3_cathode'], seam['input_INTENS'],
            seam['direct_input_to_neck_passthrough']) != ('intens', 'rx_intens', False):
        raise ValueError('page-3/4 source seam changed')
    profile = json.loads(NECK_PROFILE.read_text())
    bounds = profile['parameters']['d_cjo']
    if not bounds['minimum'] < bounds['nominal'] < bounds['maximum']:
        raise ValueError('diode capacitance bounds changed')
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        baseline = folder/'baseline'
        signal_path.run(capture_path, baseline, duration=DURATION, step=STEP)
        deck = (baseline/'run.cir').read_text()
        if (deck.count(D4_LINE) != 1 or
                'Q201 intens base_i mreturn' not in deck or
                'D205 clamp_i intens' not in deck or
                'X201 rx_video rx_video video_inv rx_bsyn rx_bsyn sync_gate mreturn intensity_gate rx_intens rx_intens vid video_inv video_inv p5 T200_BOUND' not in deck):
            raise ValueError('modeled IS drive differs from source-addressed contract')
        capture = json.loads((baseline/'effective-input.json').read_text())
        variants = []
        for label, capacitance in [('nominal', bounds['nominal']),
                                   ('lower_bound', bounds['minimum']),
                                   ('upper_bound', bounds['maximum']),
                                   ('zero_cjo_diagnostic', 0)]:
            if label == 'nominal':
                samples = baseline/'samples.txt'
                variant_deck = deck
            else:
                variant_deck = deck.replace(D4_LINE, 'D4 intens brightness 1AD50_D4_CJO')
                variant_deck = variant_deck.replace('.control\n',
                    ALTERNATE_MODEL.replace('{capacitance}', f'{capacitance:.15g}')+'\n.control\n', 1)
                samples = solve(variant_deck, folder/label)
            variants.append({'case': label, 'd4_cjo_f': capacitance,
                             'deck_sha256': hashlib.sha256(variant_deck.encode()).hexdigest(),
                             'stable_states': stable_states(samples, capture['events'],
                                                            capture['clock_hz'])})
        fixed_deck = deck
        for name, value in [('video', 0), ('bsyn', 1), ('intens', 1)]:
            fixed_deck = replace_source(fixed_deck, name, value)
        fixed_samples = solve(fixed_deck, folder/'fixed_dark_video_high_intensity')
        columns, rows = read_samples(fixed_samples)
        last = rows[-1]
        fixed = {'logic_video': 0, 'logic_intensity': 1,
                 'duration_s': last[0],
                 'is_final_v': last[columns.index('receiver_intens')],
                 'cathode_final_v': last[columns.index('cathode')],
                 'deck_sha256': hashlib.sha256(fixed_deck.encode()).hexdigest()}
    return {'format': 'dac-monitor-page3-4-is-drive-diagnostic-v1',
            'qualification': 'source-addressed input/neck stage with bounded synthetic highlight stimulus; D4 capacitance sweep is diagnostic and does not identify the original IS bias network',
            'capture_sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'signal_path_sha256': hashlib.sha256((ROOT/'signal_path.py').read_bytes()).hexdigest(),
            'source_read_sha256': hashlib.sha256(SEAM.read_bytes()).hexdigest(),
            'neck_profile_sha256': hashlib.sha256(NECK_PROFILE.read_bytes()).hexdigest(),
            'duration_s': DURATION, 'step_s': STEP, 'settle_exclusion_s': SETTLE,
            'variants': variants, 'fixed_state': fixed,
            'interpretation': 'In the current model, the high IS interval while video is dark and intensity input is high depends on V2:4 (D4) junction capacitance: removing only that capacitance collapses the interval, and fixed inputs settle with IS low. With video bright, IS remains low for either intensity input. This does not prove which original page-3/4 junction or bias component is missing; the contrast/service response remains unqualified.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    arguments = parser.parse_args()
    report = run(arguments.capture)
    arguments.output.write_text(json.dumps(report, indent=2)+'\n')
    print('IS drive diagnostic:', len(report['variants']), 'capacitance cases and fixed-input solve')
