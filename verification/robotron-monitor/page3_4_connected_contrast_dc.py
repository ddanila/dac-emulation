"""DC screen of the manual Fig. 6 contrast wiring in the full ideal-rail deck.

This is a conditional topology comparison. A DC point has no flyback high
voltage or periodic scan, so it cannot qualify a sustained frame or identify
the factory page-3/4 connections.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import steady_supply
import transformer_candidates


ROOT = Path(__file__).resolve().parent
READ = ROOT/'reference/k7222-11/page3-r11-r37-source-read.json'
SOURCES = ROOT/'sources.json'
CONTRAST_POSITIONS = (.05, .95)
INCOMING_INTENS_STATES = (0, 1)
PROBES = ('cathode', 'intens', 'contrast_low', 'reference9', 'p35', 'v1_base', 'eht')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def replace_exact(deck, old, new):
    lines = deck.splitlines()
    if lines.count(old) != 1:
        raise ValueError('expected one assembled element: '+old)
    return '\n'.join(new if line == old else line for line in lines)+'\n'


def manual_terminal_variant(deck):
    """The three Fig. 6 terminal differences, with all other parts unchanged."""
    for old, new in (
        ('Q201 intens base_i 0 SC60A_CLASS_N',
         'Q201 contrast_low base_i 0 SC60A_CLASS_N'),
        ('Q202 p35 v1_base contrast_low SC60A_CLASS_N',
         'Q202 p35 v1_base intens SC60A_CLASS_N'),
        ('R213 contrast_low 0 5100.0', 'R213 intens 0 5100.0'),
    ):
        deck = replace_exact(deck, old, new)
    return deck


def dc_variant(deck, video, incoming_intens):
    lines = []
    replaced = set()
    for line in deck.splitlines():
        for signal, value in (('video', video), ('bsyn', 1),
                              ('intens', incoming_intens)):
            if line.startswith('Vlogic_'+signal+' '):
                if signal in replaced:
                    raise ValueError('duplicate logic source: '+signal)
                line = f'Vlogic_{signal} logic_{signal} computer_return DC {value}'
                replaced.add(signal)
                break
        if line.startswith(('.save ', '.tran ')):
            continue
        if line == '.end':
            lines += ['.control', 'op',
                      'print '+' '.join(f'v({name})' for name in PROBES),
                      '.endc']
        lines.append(line)
    if replaced != {'video', 'bsyn', 'intens'} or lines[-1] != '.end':
        raise ValueError('incomplete connected deck')
    return '\n'.join(lines)+'\n'


def operating_point(deck, directory):
    directory.mkdir()
    (directory/'run.cir').write_text(deck)
    result = subprocess.run(['ngspice', '-b', 'run.cir'], cwd=directory,
                            text=True, capture_output=True, timeout=45)
    log = result.stdout+'\n'+result.stderr
    if result.returncode or 'No. of Data Rows : 1' not in log:
        raise RuntimeError('ngspice DC point failed: '+log[-2000:])
    voltages = {}
    for name in PROBES:
        match = re.search(r'^v\('+re.escape(name)+r'\)\s*=\s*([+-]?[\d.eE+-]+)\s*$',
                          log, re.MULTILINE)
        if not match:
            raise ValueError('missing DC probe '+name+': '+log[-1000:])
        voltages[name+'_v'] = float(match.group(1))
    return voltages


def run():
    page3 = json.loads(READ.read_text())
    nets = {row['name']: row['terminals'] for row in page3['source_nets']}
    if 'V5:lower_right' not in nets['00']:
        raise ValueError('V5 return source read changed')
    sources = {row['file']: row['sha256'] for row in json.loads(SOURCES.read_text())['sources']}
    selection = {'status': 'complete', 'period_ticks': 3600000,
                 'clock_hz': 179712000,
                 'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
    rows = []
    dark_rows = []
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        assembly = steady_supply.assemble(folder/'assembly')
        candidate = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])[0]
        assembly['parameters']['brightness_position'] = 0
        for contrast in CONTRAST_POSITIONS:
            assembly['parameters']['contrast_position'] = contrast
            detailed, _ = steady_supply.deck(assembly, selection, candidate)
            if detailed.count('Rcontrast reference9 contrast_low ') != 1 or detailed.count('D205 clamp_i intens ') != 1:
                raise ValueError('contrast or neck topology differs from fixture')
            for topology, deck in (('detailed_page3_4', detailed),
                                   ('manual_fig6_terminal_swap', manual_terminal_variant(detailed))):
                for incoming in INCOMING_INTENS_STATES:
                    static = dc_variant(deck, 1, incoming)
                    values = operating_point(static, folder/f'{topology}-{contrast}-{incoming}')
                    rows.append(dict(topology=topology,
                                     contrast_position=contrast,
                                     brightness_position=0,
                                     raw_incoming_intens=incoming,
                                     video=1,
                                     dc_deck_sha256=sha(static.encode()),
                                     **values))
        assembly['parameters']['contrast_position'] = .5
        detailed, _ = steady_supply.deck(assembly, selection, candidate)
        for topology, deck in (('detailed_page3_4', detailed),
                               ('manual_fig6_terminal_swap', manual_terminal_variant(detailed))):
            for incoming in INCOMING_INTENS_STATES:
                static = dc_variant(deck, 0, incoming)
                values = operating_point(static, folder/f'dark-{topology}-{incoming}')
                dark_rows.append(dict(topology=topology,
                                      contrast_position=.5,
                                      brightness_position=0,
                                      raw_incoming_intens=incoming,
                                      video=0,
                                      dc_deck_sha256=sha(static.encode()),
                                      **values))
        assembly_hashes = assembly['hashes']
    swings = []
    for topology in ('detailed_page3_4', 'manual_fig6_terminal_swap'):
        for incoming in INCOMING_INTENS_STATES:
            pair = [r for r in rows if r['topology'] == topology and
                    r['raw_incoming_intens'] == incoming]
            low, high = sorted(pair, key=lambda r: r['contrast_position'])
            swings.append(dict(topology=topology, raw_incoming_intens=incoming,
                               cathode_delta_v=high['cathode_v']-low['cathode_v']))
    return dict(format='dac-monitor-page3-4-connected-contrast-dc-v1',
                qualification='full ideal-rail assembly at DC with fixed video and sync; no flyback EHT, periodic scan, qualified tube response or connected native-grid score',
                alternative_status='conditional manual Fig. 6 terminal wiring; detailed page-3/4 source schematic and KiCad assembly remain unchanged',
                source_pdf_sha256={'schematic': sources['older.pdf'],
                                   'manual': sources['older-operation.pdf']},
                source_pages={'detailed_schematic': [3, 4],
                              'manual_functional_figure': 11},
                page3_source_read_sha256=sha(READ.read_bytes()),
                steady_supply_sha256=sha((ROOT/'steady_supply.py').read_bytes()),
                assembly_hashes=assembly_hashes,
                winding_candidate_id=candidate['id'],
                v4_breakdown_v=9.1,
                logic_note='The provisional T200 model inverts raw incoming INTENS before V5; raw state numbers cannot be compared directly with the manual regenerated intensity signal.',
                rows=rows, dark_rows=dark_rows,
                contrast_cathode_swings=swings)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('connected DC points:', len(report['rows'])+len(report['dark_rows']))
