"""Bound the IS drive needed by the source-addressed neck stage.

This replaces only main-board V5 with a fixed Thevenin source for each DC
solve. It is a boundary diagnostic, not a source claim or a connected-frame
fallback. The manual's contrast transfer remains outside this fixture.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import signal_path
from page18_contrast_dc_diagnostic import replace_line


ROOT = Path(__file__).resolve().parent
PAGE3_READ = ROOT/'reference/k7222-11/page3-r11-r37-source-read.json'
NECK_READ = ROOT/'reference/k7222-11/page16-neck-source-netlist.json'
SOURCES = ROOT/'sources.json'
LEVELS_V = (0, 5, 10, 15, 15.7, 16)
RESISTANCES_OHM = (0, 10, 100, 1000, 10000)


def op(deck, folder, video, source_v, resistance_ohm):
    deck = replace_line(deck, 'Vlogic_video ', f'Vlogic_video logic_video 0 {video}')
    deck = replace_line(deck, 'Vlogic_intens ', 'Vlogic_intens logic_intens 0 0')
    lines = deck.splitlines()
    lines = [line for line in lines if not line.startswith('Q201 intens base_i mreturn ')]
    if len(lines) != len(deck.splitlines())-1:
        raise ValueError('V5 model not found exactly once')
    circuit = '\n'.join(lines).split('.control\n', 1)[0]
    if resistance_ohm:
        circuit += (f'VISBOUND is_supply mreturn {source_v}\n'
                    f'RISBOUND is_supply intens {resistance_ohm}\n')
    else:
        circuit += f'VISBOUND intens mreturn {source_v}\n'
    circuit += ('.control\nset noaskquit\nop\n'
                'print v(intens,mreturn) v(cathode,mreturn) i(VISBOUND)\n'
                'quit\n.endc\n.end\n')
    folder.mkdir()
    (folder/'run.cir').write_text(circuit)
    result = subprocess.run(['ngspice', '-b', 'run.cir'], cwd=folder,
                            capture_output=True, text=True)
    log = result.stdout+result.stderr
    if result.returncode or 'Error:' in log:
        raise RuntimeError('IS boundary solve failed: '+log[-500:])
    values = dict((name.lower(), float(value)) for name, value in re.findall(
        r'(?m)^([^\s=]+)\s+=\s+([-+0-9.eE]+)\s*$', log))
    required = ('v(intens,mreturn)', 'v(cathode,mreturn)', 'i(visbound)')
    if any(name not in values for name in required):
        raise ValueError('IS boundary operating-point probes missing')
    return {'video_logic': video, 'source_voltage_v': source_v,
            'source_resistance_ohm': resistance_ohm,
            'is_v': values['v(intens,mreturn)'],
            'cathode_v': values['v(cathode,mreturn)'],
            'source_delivered_current_a': -values['i(visbound)'],
            'deck_sha256': hashlib.sha256(circuit.encode()).hexdigest()}


def run(capture_path):
    capture_path = Path(capture_path)
    page3 = json.loads(PAGE3_READ.read_text())
    nets = {row['name']: row['terminals'] for row in page3['source_nets']}
    if 'V5:lower_right' not in nets['00'] or 'V5:lower_right' in nets['12P']:
        raise ValueError('V5 source return not settled at 00')
    neck = json.loads(NECK_READ.read_text())
    if neck.get('signal_polarity') != {'IS_low': 'intensive', 'IS_high': 'normal'}:
        raise ValueError('neck IS polarity read changed')
    sources = {row['file']: row['sha256'] for row in json.loads(SOURCES.read_text())['sources']}
    with tempfile.TemporaryDirectory() as directory:
        folder = Path(directory)
        signal_path.run(capture_path, folder/'baseline', duration=1e-5, step=5e-9)
        deck = (folder/'baseline'/'run.cir').read_text()
        if ('Q201 intens base_i mreturn ' not in deck or
                'D205 clamp_i intens ' not in deck or
                'D4 intens brightness ' not in deck or
                'Ibeam mreturn cathode 20u' not in deck):
            raise ValueError('source-addressed IS/neck boundary changed')
        ideal = [op(deck, folder/f'ideal-{index}-{video}', video, level, 0)
                 for index, level in enumerate(LEVELS_V) for video in (0, 1)]
        resistance = [op(deck, folder/f'load-{index}', 1, 15.7, value)
                      for index, value in enumerate(RESISTANCES_OHM)]
    target = next(row for row in ideal if row['video_logic'] == 1 and
                  row['source_voltage_v'] == 15.7)
    return {'format': 'dac-monitor-page3-4-is-boundary-requirement-v1',
            'qualification': 'fixed-logic, ideal-rail input/neck diagnostic with 20 microampere fixed cathode load; V5 is replaced only for this test; no original IS driver, contrast transfer, tube emission or connected-frame claim',
            'capture_sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'signal_path_sha256': hashlib.sha256((ROOT/'signal_path.py').read_bytes()).hexdigest(),
            'page3_source_sha256': hashlib.sha256(PAGE3_READ.read_bytes()).hexdigest(),
            'neck_source_sha256': hashlib.sha256(NECK_READ.read_bytes()).hexdigest(),
            'manual_source': {'file': 'older-operation.pdf',
                              'sha256': sources['older-operation.pdf'],
                              'pdf_pages': [10, 11],
                              'dark_cathode_approx_v': 35,
                              'normal_bright_cathode_approx_v': 15},
            'ideal_source_levels_v': list(LEVELS_V),
            'series_resistances_ohm': list(RESISTANCES_OHM),
            'ideal_source_rows': ideal,
            'series_resistance_rows': resistance,
            'nominal_boundary_example': target,
            'interpretation': 'With V5 replaced by an ideal IS boundary source, the existing neck stage reaches about 15 V normal-bright cathode at 15.7 V IS while dark video stays near 33.69 V. The ideal source delivers about 28.7 mA during bright video; 100 ohm source resistance drops the cathode to about 12.66 V. These are requirements for any labelled equivalent, not evidence that the original V5 stage supplies them.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.capture)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('IS boundary:', len(report['ideal_source_rows']), 'ideal and',
          len(report['series_resistance_rows']), 'resistance operating points')
