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
PAGE3_READ = ROOT/'reference/k7222-11/page3-r11-r37-source-read.json'
INVENTORY = ROOT/'reference/k7222-11/inventory.json'
SOURCES = ROOT/'sources.json'
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
    page3 = json.loads(PAGE3_READ.read_text())
    source_nets = {row['name']: row['terminals'] for row in page3['source_nets']}
    if ('V5:lower_right' not in source_nets['00'] or
            'V5:lower_right' in source_nets['12P']):
        raise ValueError('page-3 V5 return source read differs from DC fixture')
    parts = json.loads(INVENTORY.read_text())['parts']
    v4 = next(part for part in parts if part['id'] == '012-6921:V4')
    if v4['description'] != '9.1 ZC':
        raise ValueError('page-8 V4 zener parts-list read changed')
    source_hashes = {row['file']: row['sha256'] for row in json.loads(SOURCES.read_text())['sources']}
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
        zener_lines = [line for line in deck.splitlines()
                       if line.startswith('.model Z9_BOUND ')]
        if len(zener_lines) != 1 or 'BV=9.1 ' not in zener_lines[0]:
            raise ValueError('active V4 zener model differs from 9.1 V source value')
        manual_variant_deck = deck.replace(zener_lines[0],
                                           zener_lines[0].replace('BV=9.1 ', 'BV=15 '))
        rows = [operating_point(deck, folder/f'op-{feed}-{video}-{intensity}-{position}',
                                position, video, intensity, feed)
                for feed in FEED_RESISTANCES
                for video, intensity in STATES
                for position in CONTRAST_POSITIONS]
        manual_variant_rows = [operating_point(
            manual_variant_deck, folder/f'v4-15-{intensity}-{position}',
            position, 1, intensity, 0)
            for intensity in (0, 1) for position in CONTRAST_POSITIONS]
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
    return {'format': 'dac-monitor-page18-contrast-dc-diagnostic-v3',
            'qualification': 'fixed-logic DC operating points in the source-addressed input/neck bench; 100 ohm 35 V feed impedance is illustrative only, not a sourced model or manual service procedure',
            'input_sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'signal_path_sha256': hashlib.sha256((ROOT/'signal_path.py').read_bytes()).hexdigest(),
            'intensity_seam_source_sha256': hashlib.sha256(INTENS_SEAM.read_bytes()).hexdigest(),
            'page3_source_read_sha256': hashlib.sha256(PAGE3_READ.read_bytes()).hexdigest(),
            'v4_source_conflict': {
                'factory_parts_list': {'file': 'older.pdf', 'pdf_page': 8,
                                       'pdf_sha256': source_hashes['older.pdf'],
                                       'V4_description': v4['description']},
                'manual_functional_figure': {'file': 'older-operation.pdf',
                                             'pdf_page': 11, 'figure': 6,
                                             'reference_v': 15,
                                             'pdf_sha256': source_hashes['older-operation.pdf']},
                'hypothesis': 'Changing only the active V4 zener breakdown from 9.1 to 15 V is a diagnostic alternative, not an assertion that the factory V4 is 15 V.',
                'manual_variant_rows': manual_variant_rows},
            'contrast_positions': list(CONTRAST_POSITIONS),
            'logic_states_video_intensity': [list(state) for state in STATES],
            'feed_resistances_ohm': list(FEED_RESISTANCES),
            'rows': rows, 'comparisons': comparisons,
            'interpretation': 'The source-read seam separates incoming INTENS from the neck IS output: V5 upper lead drives neck intens, its lower lead returns to 00, and HRS drives V1 base. The parts-list 9.1 V V4 and manual Fig. 6 functional 15 V reference conflict; setting V4 breakdown to 15 V changes its local reference and V1 current but not steady IS or cathode in this scoped bench. This topology lacks a qualified high-state IS drive and does not satisfy the manual intensity or contrast response. The 100 ohm 35 V feed remains an illustrative sensitivity probe; connected native-grid response remains unqualified.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.capture)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{len(report['rows'])} contrast DC operating points completed")
