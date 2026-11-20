"""Audit one-factor attempts to cross the connected 39 ms solver boundary."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parent
TRAN = '.tran 5e-08 0.078 0 5e-08'
SHORT_TRAN = '.tran 5e-08 0.0391 0 5e-08'


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def shorten(deck):
    if deck.count(TRAN) != 1:
        raise ValueError('baseline transient command changed')
    return deck.replace(TRAN, SHORT_TRAN)


def explicit_fields(deck):
    lines = []
    period = .0195
    for line in deck.splitlines():
        if line.startswith('Vlogic_'):
            head, tail = line.split('PWL(', 1)
            points, suffix = tail.split(') r=0', 1)
            tokens = points.split()
            if len(tokens) % 2:
                raise ValueError('odd PWL token count')
            pairs = [(float(tokens[i]), tokens[i+1])
                     for i in range(0, len(tokens), 2)]
            expanded = pairs + [(t+k*period, value) for k in (1, 2)
                                for t,value in pairs[1:]]
            if any(b[0] < a[0] for a,b in zip(expanded, expanded[1:])):
                raise ValueError('nonmonotonic explicit PWL')
            line = head+'PWL('+' '.join(f'{t:.15g} {value}'
                                       for t,value in expanded)+')'+suffix
        lines.append(line)
    return '\n'.join(lines)+'\n'


def raw_tail(path):
    with Path(path).open('rb') as stream:
        header = b''
        while not header.endswith(b'Binary:\n'):
            line = stream.readline()
            if not line or len(header) > 1_000_000:
                raise ValueError('missing raw header')
            header += line
        match = re.search(rb'No. Variables:\s+(\d+)', header)
        if match is None:
            raise ValueError('missing raw width')
        row = struct.Struct('='+str(int(match[1]))+'d')
        start = stream.tell()
        stream.seek(0, 2)
        count = (stream.tell()-start)//row.size
        if count < 2:
            raise ValueError('raw trace too short')
        stream.seek(start+(count-1)*row.size)
        return count, row.unpack(stream.read(row.size))[0]


def case(directory, expected, name, change):
    directory = Path(directory)
    deck = directory/'run.cir'
    if deck.read_text() != expected:
        raise ValueError(name+' deck differs beyond declared one-factor edit')
    solve = json.loads((directory/'solve.json').read_text())
    log = (directory/'solver.log').read_text(errors='replace')
    errors = [line.strip() for line in log.splitlines()
              if 'Timestep too small' in line or
              'run simulation(s) aborted' in line]
    rows, last_time = raw_tail(directory/'trace.raw')
    return {
        'name': name,
        'change': change,
        'deck_sha256': sha(deck),
        'solve_status': solve['status'],
        'solve_elapsed_s': solve['elapsed_s'],
        'solve_timeout': solve['timeout'],
        'raw_sha256': sha(directory/'trace.raw'),
        'raw_complete_rows': rows,
        'last_time_s': last_time,
        'crossed_39_ms': last_time > .039,
        'solver_abort_messages': errors,
    }


def summarize(baseline, bsyn, explicit, gate_tau, detailed):
    baseline = Path(baseline)
    original = (baseline/'run.cir').read_text()
    short = shorten(original)
    edge_old = '0.0194999999 1 0.0195 0'
    if short.count(edge_old) != 1 or short.count('.param gate_tau=5e-09') != 1:
        raise ValueError('baseline edge or gate delay changed')
    detailed_deck = short
    for old, new in (
        ('Q201 contrast_low base_i 0 SC60A_CLASS_N',
         'Q201 intens base_i 0 SC60A_CLASS_N'),
        ('Q202 p35 v1_base intens SC60A_CLASS_N',
         'Q202 p35 v1_base contrast_low SC60A_CLASS_N'),
        ('R213 intens 0 5100.0', 'R213 contrast_low 0 5100.0'),
    ):
        if detailed_deck.count(old) != 1:
            raise ValueError('baseline contrast topology changed')
        detailed_deck = detailed_deck.replace(old, new)
    cases = [
        case(bsyn, short.replace(edge_old, '0.01949998 1 0.0195 0'),
             'bsyn_boundary_20_ns', 'Only final BSYN transition widened from 0.1 to 20 ns.'),
        case(explicit, explicit_fields(short),
             'explicit_pwl_fields', 'Same captured logic points repeated explicitly for three fields, without PWL r=0.'),
        case(gate_tau, short.replace('.param gate_tau=5e-09',
                                     '.param gate_tau=3e-08'),
             'gate_tau_30_ns', 'T200 gate_tau raised from 5 to 30 ns, its registered exploratory upper bound.'),
        case(detailed, detailed_deck,
             'detailed_page3_4_contrast', 'Manual-Fig.-6 contrast transistor and R213 terminals returned to the transcribed page-3/4 graph.'),
    ]
    baseline_solve = json.loads((baseline/'solve.json').read_text())
    baseline_rows, baseline_end = raw_tail(baseline/'trace.raw')
    return {
        'format': 'dac-monitor-t3-field-boundary-screen-v1',
        'qualification': 'one-factor connected solver diagnostics; no source correction, sustained field or A5 freeze',
        'source_hashes': {path.name: sha(path) for path in
                          (ROOT/'t3_field_boundary_screen.py',
                           ROOT/'steady_supply.py',
                           ROOT/'reference/k7222-11/device-model-register.json')},
        'baseline': {
            'deck_sha256': sha(baseline/'run.cir'),
            'solve_status': baseline_solve['status'],
            'raw_complete_rows': baseline_rows,
            'last_time_s': baseline_end,
            'solver_abort': 'Timestep too small at 39 ms, trouble with Q201',
        },
        'shortened_endpoint_s': .0391,
        'cases': cases,
        'interpretation': ('Each case changes one declared factor and stops at 39.1 ms. '
                           'A pass only narrows a solver cause; it does not '
                           'qualify the connected monitor.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--bsyn', type=Path, required=True)
    parser.add_argument('--explicit', type=Path, required=True)
    parser.add_argument('--gate-tau', type=Path, required=True)
    parser.add_argument('--detailed', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(summarize(args.baseline, args.bsyn,
                                               args.explicit, args.gate_tau,
                                               args.detailed),
                                      indent=2)+'\n')
