#!/usr/bin/env python3
"""Run the full firmware acceptance sweep against the full-bus HDL boundary."""
import argparse
import json
import subprocess
import shutil
from pathlib import Path
from io_final_suite import producer
from io_flags_candidate import replace_once
from qualify import ROOT, sha
HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-cpu-bus-firmware')
    ap.add_argument('--production', action='store_true')
    ap.add_argument('--jobs', type=int, default=3)
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    production_sources=[ROOT/'tools/generate_keyboard_cpu.py', ROOT/'common/cpu/z80.h', ROOT/'third_party/cpu/chips/z80.h', *[ROOT/'machines/robotron1715m'/name for name in ('keyboard_board.c','keyboard_board.h','keyboard_cpu.c','keyboard_cpu.h')],*sorted((ROOT/'machines/robotron1715m/generated/keyboard_cpu').glob('*.h'))]
    production_hashes={str(p.relative_to(ROOT)):sha(p) for p in production_sources}
    if a.production:
        for p in production_sources:
            dest=out/'production'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
    original, text = producer('firmware')
    text = replace_once(text, " (out/'rom.hex').write_text", " from cpu_bus_candidate import generate as full_bus\n rtl=full_bus(out/'full-bus')+[BOARD/'chips.v',BOARD/'generated/controller.v']\n (out/'rom.hex').write_text")
    text = replace_once(text, "v=v.replace('tv80n cpu(','tv80_io_candidate cpu(')", "v=v.replace('tv80n cpu(','cpu_bus_candidate cpu(')")
    text = replace_once(text, "['iverilog','-g2012','-s','firmware_tb'", "['iverilog','-g2012','-DTV80_REFRESH','-s','firmware_tb'")
    if a.production:
        text=replace_once(text,"  # BR2 is a CPU reset", "  c=c.replace(str(root/'machines/robotron1715m/keyboard.h'),str(out/'production/machines/robotron1715m/keyboard_board.h')).replace('dac_z80_tick','k7658_cpu_tick')\n  # BR2 is a CPU reset")
        text=replace_once(text,"unsigned held_leds=k.leds;robotron_keyboard_init(&k,rom,NULL,bit);k.leds=held_leds;", "robotron_keyboard_release(&k);robotron_keyboard_reset(&k);")
        text=replace_once(text,"str(root/'machines/robotron1715m/keyboard.c'),str(root/'common/cpu/z80.c')","str(out/'production/machines/robotron1715m/keyboard_board.c'),str(out/'production/machines/robotron1715m/keyboard_cpu.c')")
    else:
        text=replace_once(text," # Regenerate the independently exercised", " from cpu_bus_runtime import integrate_shadow\n integrate_shadow(root)\n # Regenerate the independently exercised")
    script = out / 'producer.py'; script.write_text(text)
    subprocess.run(['python3', str(script), '--rom', str(a.rom.resolve()), '--out', str(out), '--jobs', str(a.jobs)], check=True)
    path = out / 'assessment.json'; report = json.loads(path.read_text())
    for p in [script, out / 'tv80_core.v', out / 'tv80_io_candidate.v']:
        report['sources'].pop(str(p.relative_to(ROOT)), None)
    for p in [Path(__file__), original, HERE/'io_final_suite.py', HERE/'io_boundary_suite.py', HERE/'cpu_bus_runtime.py', HERE/'cpu_bus_c.py', HERE/'cpu_bus_half.h', HERE/'cpu_bus_pins.h', HERE/'cpu_bus_candidate.py', HERE/'cpu_bus_candidate.v', HERE/'io_repeat_candidate.py', HERE/'io_complete_candidate.py', HERE/'io_wait_candidate.py', HERE/'io_flags_candidate.py']:
        report['sources'][str(p.relative_to(ROOT))] = sha(p)
    report['productionBackendTested']=a.production
    if a.production:
        for p,digest in production_hashes.items():
            if sha(ROOT/p)!=digest:raise ValueError('Production source changed during capture: '+p)
        report['sources'].update(production_hashes)
    report['composedArtifacts'] = {str(p.relative_to(out)): sha(p) for p in [script, *sorted((out/'full-bus').glob('*.v'))]}
    if a.production:report['composedArtifacts'].update({str(p.relative_to(out)):sha(p) for p in sorted((out/'production').rglob('*')) if p.is_file()})
    report['boundary'] = 'Full firmware C and HDL bus-boundary candidates. No bus grants are requested by this fixture; use cpu_bus_review.py for arbitration. This does not qualify C memory/refresh/interrupt pins or production integration.'
    path.write_text(json.dumps(report, indent=2) + '\n')
    if not all(report[k] for k in ('functionalAgreement', 'serialCycleAgreement', 'realLedTransitionAgreement')):
        raise SystemExit('Full-bus firmware mismatch')

if __name__ == '__main__': main()
