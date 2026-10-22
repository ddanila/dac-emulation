#!/usr/bin/env python3
"""Compose flag/WAIT experiments with existing instruction and firmware fixtures.

Keep earlier producers and their negative evidence byte-identical. Fail closed
if their integration points change; retain the composed producer for review.
"""
import argparse
import json
import subprocess
from pathlib import Path
from qualify import ROOT, sha
from io_flags_candidate import replace_once

HERE = Path(__file__).resolve().parent
IMPORTS = '''
from io_flags_candidate import generate as flags_generate
from io_wait_candidate import c_generate as wait_c, hdl_generate as wait_hdl, core_generate as wait_core
'''
HDL = '''
 (out/'tv80_core.v').write_text(wait_core(flags_generate((ROOT/'third_party/cpu/tv80/tv80_core.v').read_text())))
 (out/'tv80_io_candidate.v').write_text(wait_hdl((HERE/'tv80_io_candidate.v').read_text()))
 rtl=[p for p in rtl if p.name not in ('tv80_core.v','tv80_io_candidate.v')]+[out/'tv80_core.v',out/'tv80_io_candidate.v']
'''


def composed(kind):
    original = HERE/('c_read_instructions.py' if kind == 'instructions' else 'c_read_pair.py')
    text = original.read_text()
    text = replace_once(text, 'HERE=Path(__file__).resolve().parent',
                        f'HERE=Path({str(HERE)!r})\nimport sys\nsys.path.insert(0,str(HERE))'+IMPORTS)
    # Imports before HERE also need the original directory on the search path.
    text = 'import sys\nsys.path.insert(0,'+repr(str(HERE))+')\n'+text
    if kind == 'instructions':
        text = replace_once(text, " half=(HERE/'c_read_instructions.c').read_text()", " (out/'c_read_half.h').write_text(wait_c((HERE/'c_read_half.h').read_text()))\n half=(HERE/'c_read_instructions.c').read_text()")
        text = replace_once(text, " run(['iverilog','-g2012','-s','c_read_instructions','-o'", HDL+" run(['iverilog','-g2012','-s','c_read_instructions','-o'")
    else:
        text = replace_once(text, "header=(HERE/'c_read_half.h').read_text().replace", "header=wait_c((HERE/'c_read_half.h').read_text()).replace")
        text = replace_once(text, " (out/'rom.hex').write_text", HDL+" (out/'rom.hex').write_text")
    return original, text


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('kind', choices=['instructions','firmware'])
    ap.add_argument('--rom', type=Path)
    ap.add_argument('--out', type=Path)
    ap.add_argument('--jobs', type=int, default=3)
    a = ap.parse_args()
    out = (a.out or ROOT/('build/keyboard-controller-io-boundary-'+a.kind)).resolve()
    out.mkdir(parents=True, exist_ok=True)
    original, text = composed(a.kind)
    producer = out/'producer.py'; producer.write_text(text)
    cmd = ['python3', str(producer), '--out', str(out)]
    if a.kind == 'firmware':
        if not a.rom: ap.error('--rom required for firmware')
        cmd += ['--rom', str(a.rom.resolve()), '--jobs', str(a.jobs)]
    subprocess.run(cmd, check=True)
    path = out/'assessment.json'; report = json.loads(path.read_text())
    for generated in [producer,out/'tv80_core.v',out/'tv80_io_candidate.v']:
        report['sources'].pop(str(generated.relative_to(ROOT)),None)
    for p in [Path(__file__), original, HERE/'io_flags_candidate.py', HERE/'io_wait_candidate.py']:
        report['sources'][str(p.relative_to(ROOT))] = sha(p)
    report['composedArtifacts'] = {p.name:sha(p) for p in [producer,out/'tv80_core.v',out/'tv80_io_candidate.v']}
    report['profile'] = 'I/O normal-completion flags plus falling-edge read WAIT; experimental'
    report['qualified'] = False
    path.write_text(json.dumps(report, indent=2)+'\n')
    if a.kind == 'instructions':
        if not report['allLateCasesAgree']: raise SystemExit('Combined instruction/flags mismatch')
    elif not all(report[k] for k in ('functionalAgreement','serialCycleAgreement','realLedTransitionAgreement')):
        raise SystemExit('Combined firmware mismatch')

if __name__ == '__main__':
    main()
