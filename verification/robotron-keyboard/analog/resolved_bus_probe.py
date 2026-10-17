#!/usr/bin/env python3
"""Check schematic ROM addressing, bus release and digital driver contention."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from controller_interface import generate

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-analog/resolved-bus')
    a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
    report={'passed':False,'scope':__doc__,
            'limitation':'Resolved logic states only; no electrical bus currents, pin delays or drive-strength calibration',
            'sources':{name:sha(HERE/name) for name in ('resolved_bus_probe.py','resolved_bus_tb.v','controller_interface.py','logic_control.py','circuit.py')},
            'chipsSha256':sha(HERE.parent/'chips.v')}
    try:
        (out/'controller_analog.v').write_text(generate(explicit_cpu_drive=True,resolved_bus=True))
        report['generatedSha256']=sha(out/'controller_analog.v')
        subprocess.run(['iverilog','-g2012','-s','resolved_bus_tb','-o',str(out/'bus.vvp'),
                        str(HERE.parent/'chips.v'),str(out/'controller_analog.v'),str(HERE/'resolved_bus_tb.v')],check=True)
        proc=subprocess.run(['vvp','bus.vvp'],cwd=out,capture_output=True,text=True,timeout=60)
        (out/'hdl.log').write_text(proc.stdout+proc.stderr)
        proc.check_returncode()
        if 'RESOLVED_BUS_PASS' not in proc.stdout:raise ValueError('Bus checks did not complete')
        report['passed']=True
    except Exception as error:
        report['error']=str(error);raise
    finally:(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'report.json')


if __name__=='__main__':main()
