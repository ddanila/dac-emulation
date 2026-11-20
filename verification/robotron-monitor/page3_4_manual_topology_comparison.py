"""Compare the detailed page-3/4 contrast graph with manual Fig. 6.

The manual alternative changes only the V1/V5 output terminal assignments and
the V1 shunt node. It is a document-conflict diagnostic, not an adopted
factory connection or a calibrated intensity/contrast stage.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import signal_path
import steady_supply
from page18_contrast_dc_diagnostic import operating_point, replace_line


ROOT = Path(__file__).resolve().parent
SEAM = ROOT/'reference/k7222-11/page3-4-intens-seam-source-read.json'
PAGE3 = ROOT/'reference/k7222-11/page3-r11-r37-source-read.json'
INVENTORY = ROOT/'reference/k7222-11/inventory.json'
SOURCES = ROOT/'sources.json'
BRIGHTNESS = (0, .5)
CONTRAST = (.05, .95)
INCOMING_INTENS = (0, 1)


def alter_v4(deck, breakdown_v):
    if breakdown_v == 9.1:
        return deck
    lines = [line for line in deck.splitlines() if line.startswith('.model Z9_BOUND ')]
    if len(lines) != 1 or 'BV=9.1 ' not in lines[0]:
        raise ValueError('source-list V4 model is not 9.1 V')
    return deck.replace(lines[0], lines[0].replace('BV=9.1 ', f'BV={breakdown_v} '))


def with_brightness(deck, position):
    top, bottom = steady_supply.brightness_resistances(position, 10000)
    deck = replace_line(deck, 'Rbrightness_top ',
                        f'Rbrightness_top p35 v1_base {top:.15g}')
    return replace_line(deck, 'Rbrightness_bottom ',
                        f'Rbrightness_bottom v1_base contrast_adjust {bottom:.15g}')


def manual_figure_topology(deck):
    deck = replace_line(deck, 'Q201 intens base_i mreturn ',
                        'Q201 contrast_low base_i mreturn SC60A_CLASS_N')
    deck = replace_line(deck, 'Q202 p35 v1_base contrast_low ',
                        'Q202 p35 v1_base intens SC60A_CLASS_N')
    return replace_line(deck, 'R213 contrast_low mreturn ',
                        'R213 intens mreturn 5100')


def run(capture_path):
    capture_path = Path(capture_path)
    seam = json.loads(SEAM.read_text())['model_correction']
    if (seam['V5_collector_and_V3_cathode'], seam['input_INTENS'],
            seam['direct_input_to_neck_passthrough']) != ('intens', 'rx_intens', False):
        raise ValueError('page-3/4 seam source read changed')
    page3 = json.loads(PAGE3.read_text())
    nets = {row['name']: row['terminals'] for row in page3['source_nets']}
    if 'V5:lower_right' not in nets['00']:
        raise ValueError('V5 source return no longer at 00')
    parts = json.loads(INVENTORY.read_text())['parts']
    v4 = next(row for row in parts if row['id'] == '012-6921:V4')
    if v4['description'] != '9.1 ZC':
        raise ValueError('factory V4 parts-list value changed')
    sources = {row['file']: row['sha256'] for row in json.loads(SOURCES.read_text())['sources']}
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        signal_path.run(capture_path, folder/'baseline', duration=1e-5, step=5e-9)
        deck = (folder/'baseline'/'run.cir').read_text()
        required = ('Q201 intens base_i mreturn ',
                    'Q202 p35 v1_base contrast_low ',
                    'R213 contrast_low mreturn ',
                    'Rcontrast reference9 contrast_low ',
                    'D205 clamp_i intens ')
        if any(deck.count(line) != 1 for line in required):
            raise ValueError('detailed contrast graph differs from comparison fixture')
        variants = [('detailed_page3_4', 9.1, deck),
                    ('manual_fig6_terminal_swap', 9.1, manual_figure_topology(deck)),
                    ('manual_fig6_terminal_swap_v4_15_diagnostic', 15,
                     alter_v4(manual_figure_topology(deck), 15))]
        rows = []
        for label, breakdown, variant in variants:
            for brightness in BRIGHTNESS:
                variant_brightness = with_brightness(variant, brightness)
                for incoming in INCOMING_INTENS:
                    for contrast in CONTRAST:
                        case = operating_point(
                            variant_brightness,
                            folder/f'op-{label}-{brightness}-{incoming}-{contrast}',
                            contrast, 1, incoming, 0)
                        rows.append({'topology': label, 'v4_breakdown_v': breakdown,
                                     'brightness_position': brightness, **case})
        dark_rows = []
        for label, breakdown, variant in variants:
            case = operating_point(with_brightness(variant, 0),
                                   folder/f'dark-{label}', .5, 0, 0, 0)
            dark_rows.append({'topology': label, 'v4_breakdown_v': breakdown,
                              'brightness_position': 0, **case})
    return {'format': 'dac-monitor-page3-4-manual-topology-comparison-v1',
            'qualification': 'fixed-logic ideal-rail input/neck bench; alternative terminal wiring is from manual functional Fig. 6 and is not a source-validated page-3/4 replacement or connected-frame score',
            'capture_sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'signal_path_sha256': hashlib.sha256((ROOT/'signal_path.py').read_bytes()).hexdigest(),
            'seam_source_sha256': hashlib.sha256(SEAM.read_bytes()).hexdigest(),
            'page3_source_sha256': hashlib.sha256(PAGE3.read_bytes()).hexdigest(),
            'source_pdfs': {'older.pdf': sources['older.pdf'],
                            'older-operation.pdf': sources['older-operation.pdf']},
            'source_pages': {'detailed_schematic': [3, 4], 'parts_list': 8,
                             'manual_functional_figure': 11},
            'factory_v4_description': v4['description'],
            'topology_changes': [
                'V5 upper lead from IS to the external contrast wiper/low contact',
                'V1 lower lead from that contact to IS',
                'the 5100 ohm V1 emitter shunt from that contact to IS'],
            'unchanged': 'V3 diode, T200 logic, class transistor models, ideal rails, external R1/R2 bounds and neck board',
            'brightness_positions': list(BRIGHTNESS),
            'contrast_positions': list(CONTRAST),
            'incoming_intens_states': list(INCOMING_INTENS),
            'rows': rows, 'dark_rows': dark_rows,
            'interpretation': 'The detailed topology leaves the bright cathode near 0.34 V with no R2 response. The manual terminal swap at factory-list V4=9.1 V can put the bright cathode at 13.56–16.48 V and move it by about 2.92 V across R2 at the tested brightness endpoint, but the response occurs for incoming INTENS=0, while the manual discusses INTENS=1. The 15 V zener diagnostic shifts levels but does not resolve that polarity mismatch. The alternative is not selected as the active topology.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.capture)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('manual topology comparison:', len(report['rows']), 'bright and',
          len(report['dark_rows']), 'dark operating points')
