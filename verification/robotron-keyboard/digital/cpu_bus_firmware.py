#!/usr/bin/env python3
"""Run the full firmware acceptance sweep against the full-bus HDL boundary."""
import argparse
import json
import subprocess
from pathlib import Path
from io_final_suite import producer
from io_flags_candidate import replace_once
from qualify import ROOT, sha
HERE = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--rom', type=Path, required=True)
    ap.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-cpu-bus-firmware')
    ap.add_argument('--jobs', type=int, default=3)
    a = ap.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
    original, text = producer('firmware')
    text = replace_once(text, " (out/'rom.hex').write_text", " from cpu_bus_candidate import generate as full_bus\n rtl=full_bus(out/'full-bus')+[BOARD/'chips.v',BOARD/'generated/controller.v']\n (out/'rom.hex').write_text")
    text = replace_once(text, "v=v.replace('tv80n cpu(','tv80_io_candidate cpu(')", "v=v.replace('tv80n cpu(','cpu_bus_candidate cpu(')")
    text = replace_once(text, "['iverilog','-g2012','-s','firmware_tb'", "['iverilog','-g2012','-DTV80_REFRESH','-s','firmware_tb'")
    script = out / 'producer.py'; script.write_text(text)
    subprocess.run(['python3', str(script), '--rom', str(a.rom.resolve()), '--out', str(out), '--jobs', str(a.jobs)], check=True)
    path = out / 'assessment.json'; report = json.loads(path.read_text())
    for p in [script, out / 'tv80_core.v', out / 'tv80_io_candidate.v']:
        report['sources'].pop(str(p.relative_to(ROOT)), None)
    for p in [Path(__file__), original, HERE/'io_final_suite.py', HERE/'io_boundary_suite.py', HERE/'cpu_bus_candidate.py', HERE/'cpu_bus_candidate.v', HERE/'io_repeat_candidate.py', HERE/'io_complete_candidate.py', HERE/'io_wait_candidate.py', HERE/'io_flags_candidate.py']:
        report['sources'][str(p.relative_to(ROOT))] = sha(p)
    report['composedArtifacts'] = {str(p.relative_to(out)): sha(p) for p in [script, *sorted((out/'full-bus').glob('*.v'))]}
    report['boundary'] = 'Full firmware C I/O candidate versus refresh-enabled HDL bus boundary. No bus grants are requested by this fixture; use cpu_bus_review.py for arbitration. This does not qualify C memory/refresh/interrupt pins or production integration.'
    path.write_text(json.dumps(report, indent=2) + '\n')
    if not all(report[k] for k in ('functionalAgreement', 'serialCycleAgreement', 'realLedTransitionAgreement')):
        raise SystemExit('Full-bus firmware mismatch')

if __name__ == '__main__': main()
