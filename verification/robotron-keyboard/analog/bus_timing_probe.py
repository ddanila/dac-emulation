#!/usr/bin/env python3
"""Verify TV80 write-data setup/hold through the mixed-signal HDL boundary."""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

from controller_interface import generate

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, default=ROOT/'build/keyboard-controller-analog/bus-timing')
    p.add_argument('--iverilog', default='iverilog')
    p.add_argument('--vvp', default='vvp')
    args = p.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    report_path = out/'report.json'
    report_path.unlink(missing_ok=True)
    report = {'passed': False, 'scope': __doc__,
              'reference': 'https://www.zilog.com/docs/z80/um0080.pdf#page=23',
              'assumptions': {'clockPeriodNs': 10, 'waitStates': 'TV80 default; no externally requested waits',
                              'fixture': 'Synthetic alternating-zero/one memory and I/O writes, not S600 qualification',
                              'boundary': 'Digital drive-enable timing only; physical ROM/bus contention and pin delays remain unqualified'},
              'sources': {name: sha(HERE/name) for name in ('bus_timing_probe.py', 'bus_timing_tb.v',
                           'boot_cosim.v', 'controller_interface.py', 'logic_control.py', 'circuit.py')}}
    try:
        tv80 = ROOT/'third_party/cpu/tv80'
        source = json.loads((tv80/'SOURCE.json').read_text())
        for name, digest in source['files'].items():
            if sha(tv80/name) != digest:
                raise ValueError('TV80 source differs: '+name)
        report['tv80'] = source
        # LD A,0; LD HL,1000h; loop: LD (HL),A; OUT (80h),A; XOR 1; JR loop.
        program = bytes.fromhex('3e 00 21 00 10 77 d3 80 ee 01 18 f9')
        rom = program + bytes(2048-len(program))
        (out/'s600.hex').write_text('\n'.join(f'{b:02x}' for b in rom)+'\n')
        report['syntheticRomSha256'] = hashlib.sha256(rom).hexdigest()
        (out/'controller_analog.v').write_text(generate(explicit_cpu_drive=True, resolved_bus=True))
        hdl = [*sorted(tv80.glob('*.v')), HERE.parent/'chips.v', HERE.parent/'generated/controller.v',
               out/'controller_analog.v', HERE/'boot_cosim.v', HERE/'bus_timing_tb.v']
        report['hdlSha256'] = {str(path):sha(path) for path in hdl}
        subprocess.run([args.iverilog,'-g2012','-s','bus_timing_tb','-o',str(out/'bus.vvp'),*map(str,hdl)],check=True)
        proc = subprocess.run([args.vvp,'bus.vvp'],cwd=out,capture_output=True,text=True,timeout=60)
        log = proc.stdout+proc.stderr
        (out/'hdl.log').write_text(log)
        proc.check_returncode()
        if re.search(r'warning|error|fatal',log,re.I) or 'BUS_TIMING_PASS ' not in log:
            raise ValueError('Bus timing fixture did not pass cleanly')
        report['setupSamples'] = [line.split() for line in re.findall(r'^SETUP (.+)$',log,re.M)]
        report['iverilog'] = subprocess.run([args.iverilog,'-V'],capture_output=True,text=True,check=True).stdout.splitlines()[0]
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report_path.write_text(json.dumps(report,indent=2)+'\n')
    print(report_path)


if __name__ == '__main__':
    main()
