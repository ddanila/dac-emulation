#!/usr/bin/env python3
"""Compare component-fault experiments with independently captured MB001 data.

No observed bytes are passed to the native model. Full-prefix comparisons start
at the first fetch; no alignment search or oracle replay is permitted.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
ROM_SHA = '51cb80639b5667f2611da71ce7305061566cf3474bda7db6fc82709d08e46d01'


def configurations():
    def case(fault='healthy', floating='fixed', bias=255, decay=0, mask=0,
             value=0, seed=0, initial=None, pattern='seed'):
        return [fault, floating, bias, decay, mask, value, seed, 4096,
                bias if initial is None else initial, pattern]
    yield case()
    for fault in ['rom-oe-high', 'rd-buffer-high']:
        for bus in ['fixed', 'hold']:
            for bias in range(256):
                yield case(fault, bus, bias)
        for target in [0, 8, 255]:
            for initial in [0, 8, 255]:
                for delay in [1, 2, 3, 4, 5, 6, 8, 12, 16, 32]:
                    yield case(fault, 'decay', target, delay, initial=initial)
    for bias in [0, 8, 255]:
        for bus in ['fixed', 'hold']:
            yield case('rom-ce-high', bus, bias)
        yield case('data-buffer-open', bias=bias)
    for bit in range(16):
        for value in [0, 1 << bit]:
            for seed in [0, 1, 2, 3]:
                yield case('address-mask', mask=1 << bit, value=value, seed=seed)
    for fault in ['data-mask', 'rom-data-mask']:
        for bit in range(8):
            for value in [0, 1 << bit]:
                yield case(fault, mask=1 << bit, value=value)
        # Explicit multi-bit hypothesis that changes the first ROM byte 21->08.
        # Scored normally; never treated as sufficient because one byte matches.
        yield case(fault, mask=0x29, value=8)
    for seed in range(18):
        yield case('ram-contention', seed=seed)
    for fault in ['decoder-ram-alias', 'decoder-ram-alias-d3-high']:
        for retained_bits in range(1, 17):
            mask = (0xffff << retained_bits) & 0xffff
            for low, high in [(0,255),(8,255),(255,0),(255,8)]:
                for bit in [0,1,2,3,4,5,6]:
                    yield case(fault, mask=mask, pattern=f'stripe:{bit}:{low}:{high}')
    # Failed high-address drivers can both miss ROM decode and alias RAM.
    # Each family ties a contiguous high-address group, rather than fitting
    # individual memory cells to the measured instruction stream.
    for retained_bits in range(1, 12):
        mask = (0xffff << retained_bits) & 0xffff
        for value in [0,mask]:
            for low,high in [(0,255),(8,255)]:
                for bit in [0,1,2,3]:
                    yield case('address-mask',mask=mask,value=value,
                               pattern=f'stripe:{bit}:{low}:{high}')


def prefix(observed, modeled, fields):
    for i, (a, b) in enumerate(zip(observed, modeled)):
        if any(a[k] != b[k] for k in fields):
            return i
    return min(len(observed), len(modeled))


def compare(hardware, simulation):
    # Drop the last simulated fetch: duration/reads can be incomplete there.
    modeled = simulation['fetches'][:-1]
    scores = []
    for run in hardware['runs']:
        observed = run['fetches']
        fields = ['data', 'clocks', 'reads']
        control_fields = [k for k in ['ce', 'oe'] if k in observed[0]]
        joint = prefix(observed, modeled, fields + control_fields)
        n = min(len(observed), len(modeled))
        scores.append(dict(run=run['name'], observed_count=len(observed), compared_count=n,
                           byte_prefix=prefix(observed, modeled, ['data']),
                           timing_read_prefix=prefix(observed, modeled, ['clocks','reads']),
                           combined_prefix=joint,
                           control_mismatches=sum(any(a[k] != b[k] for k in control_fields)
                                                  for a, b in zip(observed, modeled)),
                           controls_measured=bool(control_fields),
                           reproduces_bounded_observation=joint == len(observed)))
    return scores


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', type=Path, required=True)
    parser.add_argument('--probe', type=Path, default=HERE.parents[1]/'build/pc1715-fault-probe')
    parser.add_argument('--hardware', type=Path, default=HERE/'mb001.json')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if hashlib.sha256(args.rom.read_bytes()).hexdigest() != ROM_SHA:
        parser.error('This campaign requires the recorded standard 2048-byte PC1715 ROM')
    hardware = json.loads(args.hardware.read_text())
    cases, matches = [], []
    for index, config in enumerate(configurations()):
        result = json.loads(subprocess.check_output([str(args.probe.resolve()), str(args.rom.resolve())]
                                                    + list(map(str, config))))
        scores = compare(hardware, result)
        entry = dict(id=index, parameters=dict(zip(
            ['fault','floating','bias','decay','mask','value','ram_seed','ticks','initial_bus','ram_pattern'], config)),
                     first16=result['fetches'][:16], scores=scores)
        cases.append(entry)
        matches.extend(dict(case=index, run=s['run']) for s in scores if s['reproduces_bounded_observation'])
    best = []
    for run in hardware['runs']:
        ranked = sorted(cases, key=lambda c: next(s['combined_prefix'] for s in c['scores'] if s['run']==run['name']), reverse=True)
        best.append(dict(run=run['name'], top_cases=[dict(case=c['id'], parameters=c['parameters'],
                    score=next(s for s in c['scores'] if s['run']==run['name'])) for c in ranked[:5]]))
    report = dict(rom_sha256=ROM_SHA, hardware_sha256=hashlib.sha256(args.hardware.read_bytes()).hexdigest(),
                  source_sha256={str(p.relative_to(HERE.parents[1])): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in [HERE/'probe.c', HERE/'campaign.py', HERE/'extract.py',
                                           HERE.parents[1]/'machines/robotron1715/pc1715.c',
                                           HERE.parents[1]/'common/cpu/z80.c',
                                           HERE.parents[1]/'third_party/cpu/chips/z80.h']},
                  scope='Bounded fault hypotheses, not analog validation; no hardware byte replay. '
                        'At most 128 first fetches per capture; controls constrain only the final capture.',
                  cases=len(cases), families=dict(Counter(c['parameters']['fault'] for c in cases)),
                  matches=matches, best=best, experiments=cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, separators=(',', ':'))+'\n')
    print(json.dumps({k: report[k] for k in ['cases','families','matches','best']}, indent=2))


if __name__ == '__main__':
    main()
