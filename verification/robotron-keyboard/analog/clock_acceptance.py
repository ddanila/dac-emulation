#!/usr/bin/env python3
"""Startup clock screens for explicit reference models; never device admission."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import tarfile
import subprocess

from circuit import load
from oscillator_probe import wiring
from gate_models import GATE_MODELS
from clock_voltage import inspect as voltage
from clock_timing import inspect as timing

HERE = Path(__file__).resolve().parent

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--ngspice', default='ngspice')
    ap.add_argument('--retain', type=Path, help='Retain complete lossless captures and assessment')
    a = ap.parse_args()
    a.out = a.out.resolve(); a.out.mkdir(parents=True, exist_ok=False)
    engine = Path(shutil.which(a.ngspice) or a.ngspice).resolve(strict=True)
    components, connectivity = load()
    report = dict(completed=False, qualified=False, connectivitySha256=connectivity,
        engineSha256=sha(engine), evidenceTier='published-constrained simulation',
        scope='Isolated reference oscillator with closed BR1, ideal 10 ns supply ramp, 25 C and explicit CPU capacitance. Whole startup waveform retained. No closed-board or device-admission claim.',
        identities={'primary':'К555ЛА3', 'comparison':'D100D', 'reference':'DL000'},
        sources={name:sha(HERE/name) for name in ['clock_acceptance.py','oscillator_probe.py','circuit.py','clock_voltage.py','clock_timing.py','clock_convergence.py','trace_io.py','gate_models.py','cpu_clock_limits.json']},
        cases=[], gates={'independentlyAdmittedDevice':False,'startupInclusiveClosedBoard':False},
        decision='Do not replace the external digital clock boundary with a claimed electrically qualified oscillator.',
        requiredEvidence={'tier':'bench', 'specimenRequired':False,
            'measurement':'Loose intended-family gate: loaded DC transfer around switching, high-output behavior under the reference pullup, and startup waveforms with reference RC and bounded CPU load. Record part identity, supply, temperature and probe loading. Compare levels and valid-level widths against cpu_clock_limits.json; keep part families separate.'})
    try:
        for profile, model in GATE_MODELS.items():
            for cap in (10,50):
                for supply in (4.75,5,5.25):
                    for step in (1,.5):
                        folder=a.out/f'{profile}-{cap}p-{supply}V-{step}ns';folder.mkdir()
                        (folder/'model.cir').write_bytes((HERE/model).read_bytes())
                        lines, _, _, source, cpu = wiring(components)
                        lines=[f'Ccpu {cpu} 0 {cap}p' if x.startswith('Ccpu ') else x for x in lines]
                        deck=['Reference oscillator CPU-limit screen',f'Vcc n_p5V 0 PWL(0 0 10n {supply})',
                              '.temp 25','.options reltol=1e-4 vntol=1e-7 abstol=1e-13','.include model.cir',*lines,
                              '.control','set numdgt=17','set wr_singlescale','set wr_vecnames',f'tran {step}n 20u',
                              f'wrdata clock.txt v({cpu}) v(n_p5V) v(n_OSC1) v(n_OSC2)',
                              'wrdata supply.txt v(n_p5V)','quit','.endc','.end']
                        (folder/'clock.cir').write_text('\n'.join(deck)+'\n')
                        (folder/'spinit').write_text('* No external initialization.\n')
                        row=dict(id=folder.name,profile=profile,cpuCapacitancePf=cap,supplyVolts=supply,maximumStepNs=step,
                                 modelSha256=sha(HERE/model),completed=False,passed=False)
                        report['cases'].append(row)
                        try:
                            run=subprocess.run([str(engine),'-n','-b','clock.cir'],cwd=folder,
                                env=dict(os.environ,SPICE_SCRIPTS=str(folder)),capture_output=True,text=True,timeout=60)
                            log=run.stdout+run.stderr;(folder/'ngspice.log').write_text(log)
                            row['exitCode']=run.returncode
                            if run.returncode or re.search(r'warning|error|failed|singular',log,re.I):
                                raise ValueError('Solver failure or diagnostic; see ngspice.log')
                            rows=[list(map(float,x.split())) for x in (folder/'clock.txt').read_text().splitlines()[1:]]
                            if not rows or rows[0][0]>1e-9 or rows[-1][0]<20e-6-math.ulp(20e-6):
                                raise ValueError('Incomplete startup interval')
                            # Column 2 is supply, not a reset stimulus. Reset metrics from the shared analyzer are excluded.
                            v=voltage(folder/'clock.txt',folder/'supply.txt',diagnostic_columns=2)
                            for key in ('supplyEpochs','resetBoundary'): v.pop(key,None)
                            t=timing(folder/'clock.txt',folder/'supply.txt',step,diagnostic_columns=2)
                            row.update(completed=True,voltage=v,timing=t)
                            row['passed']=bool(v['cycles']['assessedWithinSupplyRange'] and not v['cycles']['missingHighExcursion'] and not v['cycles']['missingLowExcursion'] and not v['inputRangeViolations'] and t['passed'])
                        except (ValueError,subprocess.TimeoutExpired) as error:
                            row['error']=str(error)
                        row['artifacts']={p.name:sha(p) for p in sorted(folder.iterdir()) if p.is_file()}
        report['completed']=True
        report['gates']['allReferenceScreensPassed']=all(r['passed'] for r in report['cases'])
    finally:
        (a.out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    if a.retain:
        a.retain.mkdir(parents=True, exist_ok=False)
        archive=a.retain/'captures.tar.xz'
        with tarfile.open(archive,'w:xz') as tar:
            for path in sorted(a.out.rglob('*')):
                if path.is_file(): tar.add(path,arcname=str(path.relative_to(a.out)),recursive=False)
        shutil.copyfile(a.out/'assessment.json',a.retain/'assessment.json')
        (a.retain/'retention.json').write_text(json.dumps({'format':'tar.xz','sha256':sha(archive),
            'scope':'All startup samples, decks and logs; no decimation or excluded intervals.',
            'assessmentSha256':sha(a.retain/'assessment.json')},indent=2)+'\n')
    print(a.out/'assessment.json')

if __name__ == '__main__':
    main()
