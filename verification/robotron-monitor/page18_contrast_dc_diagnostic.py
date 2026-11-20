"""Locate the weak page-18 contrast response in the assembled input/neck path.

This is a DC diagnostic under fixed logic levels, not a manual contrast test.
The 100 ohm feed case is an illustrative source-impedance sensitivity, not a
measured or selected value for the flyback-derived 35 V rail.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import signal_path

ROOT = Path(__file__).resolve().parent
INTENS_SEAM = ROOT/'reference/k7222-11/page3-4-intens-seam-source-read.json'
CONTRAST_POSITIONS = (.05, .95)
STATES = ((0, 0), (0, 1), (1, 0), (1, 1))
FEED_RESISTANCES = (0, 100)
PROBES = ('p35', 'reference9', 'v1_base', 'contrast_low', 'rx_intens',
          'intens', 'vid', 'clamp_i', 'cathode')


def replace_line(deck, prefix, replacement):
    lines = deck.splitlines()
    hits = [index for index, line in enumerate(lines) if line.startswith(prefix)]
    if len(hits) != 1:
        raise ValueError(f'expected one {prefix!r} in the signal-path deck')
    lines[hits[0]] = replacement
    return '\n'.join(lines)+'\n'


def operating_point(deck, folder, position, video, intensity, feed_resistance):
    deck = replace_line(deck, '.param contrast_position=',
                        f'.param contrast_position={position}')
    deck = replace_line(deck, 'Vlogic_video ',
                        f'Vlogic_video logic_video 0 {video}')
    deck = replace_line(deck, 'Vlogic_intens ',
                        f'Vlogic_intens logic_intens 0 {intensity}')
    if feed_resistance:
        deck = replace_line(deck, 'Vp35 ',
                            'Vp35 p35_source mreturn 35\n'
                            f'R35feed p35_source p35 {feed_resistance}')
    deck = deck.split('.control\n', 1)[0]
    expressions = [f'v({node},mreturn)' for node in PROBES]
    expressions.append('@q202[ic]')
    deck += ('.control\nset noaskquit\nop\nprint '+ ' '.join(expressions)
             +'\nquit\n.endc\n.end\n')
    folder.mkdir()
    (folder/'run.cir').write_text(deck)
    result = subprocess.run(['ngspice', '-b', 'run.cir'], cwd=folder,
                            capture_output=True, text=True)
    log = result.stdout+result.stderr
    if result.returncode or 'Error:' in log:
        raise RuntimeError('contrast DC operating point failed: '+log[-500:])
    values = dict((name, float(value)) for name, value in re.findall(
        r'(?m)^([^\s=]+)\s+=\s+([-+0-9.eE]+)\s*$', log))
    if any(expression not in values for expression in expressions):
        raise ValueError('contrast DC diagnostic probe missing from ngspice output')
    return {'feed_resistance_ohm': feed_resistance,
            'contrast_position': position, 'logic_video': video,
            'logic_intensity': intensity,
            'voltages_v': {node: values[f'v({node},mreturn)'] for node in PROBES},
            'v1_collector_current_a': values['@q202[ic]'],
            'deck_sha256': hashlib.sha256(deck.encode()).hexdigest()}


def run(capture_path):
    capture_path = Path(capture_path)
    source = json.loads(INTENS_SEAM.read_text())['model_correction']
    if (source['V5_collector_and_V3_cathode'],
            source['V1_base_and_brightness_R1_wiper'],
            source['input_INTENS'], source['direct_input_to_neck_passthrough']) != (
            'intens', 'v1_base', 'rx_intens', False):
        raise ValueError('intensity seam source read differs from DC fixture')
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        baseline = folder/'baseline'
        signal_path.run(capture_path, baseline, duration=1e-5, step=5e-9)
        deck = (baseline/'run.cir').read_text()
        if ('Q201 intens base_i mreturn ' not in deck or
                'D205 clamp_i intens ' not in deck or
                'Q202 p35 v1_base contrast_low ' not in deck or
                'Rcontrast reference9 contrast_low ' not in deck or
                'Vp35 p35 mreturn 35' not in deck):
            raise ValueError('assembled contrast path differs from expected fixture')
        rows = [operating_point(deck, folder/f'op-{feed}-{video}-{intensity}-{position}',
                                position, video, intensity, feed)
                for feed in FEED_RESISTANCES
                for video, intensity in STATES
                for position in CONTRAST_POSITIONS]
    comparisons = []
    for feed in FEED_RESISTANCES:
        for video, intensity in STATES:
            low, high = [row for row in rows
                         if row['feed_resistance_ohm'] == feed and
                         (row['logic_video'], row['logic_intensity']) == (video, intensity)]
            comparisons.append({'feed_resistance_ohm': feed,
                                'logic_video': video, 'logic_intensity': intensity,
                                'high_minus_low_voltage_v': {
                                    node: high['voltages_v'][node]-low['voltages_v'][node]
                                    for node in PROBES},
                                'high_minus_low_v1_collector_current_a':
                                high['v1_collector_current_a']-low['v1_collector_current_a']})
    return {'format': 'dac-monitor-page18-contrast-dc-diagnostic-v2',
            'qualification': 'fixed-logic DC operating points in the source-addressed input/neck bench; 100 ohm 35 V feed impedance is illustrative only, not a sourced model or manual service procedure',
            'input_sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'signal_path_sha256': hashlib.sha256((ROOT/'signal_path.py').read_bytes()).hexdigest(),
            'intensity_seam_source_sha256': hashlib.sha256(INTENS_SEAM.read_bytes()).hexdigest(),
            'contrast_positions': list(CONTRAST_POSITIONS),
            'logic_states_video_intensity': [list(state) for state in STATES],
            'feed_resistances_ohm': list(FEED_RESISTANCES),
            'rows': rows, 'comparisons': comparisons,
            'interpretation': 'The source-read seam separates incoming INTENS from the neck IS output: V5 collector drives neck intens and HRS drives V1 base. This scoped topology lacks a qualified high-state IS pull-up and does not satisfy the manual intensity or contrast response. The 100 ohm 35 V feed remains an illustrative sensitivity probe; connected native-grid response remains unqualified.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.capture)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{len(report['rows'])} contrast DC operating points completed")
