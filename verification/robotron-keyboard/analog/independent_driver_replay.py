#!/usr/bin/env python3
"""Cross-solver diagnostic of a recorded-driver circuit with explicit switch mapping."""
import argparse
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
from compare_firmware_io import sha
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify


def convert(text, engine):
    if text.count('\n.control\n') != 1:
        raise ValueError('Expected one ngspice control block')
    circuit, control = text.split('\n.control\n')
    if '.options trtol=1\n' not in circuit+'\n':
        raise ValueError('Expected explicit effective truncation tolerance')
    signals = re.findall(r'^wrdata host-trace.txt (.+)$',control,re.M)
    if len(signals) != 1:
        raise ValueError('Expected host voltage capture')
    models = {'CONTACT_NOMINAL':('100','1t'), 'SINK_NOMINAL':('20','1t')}
    source_lines = circuit.splitlines()
    lines, changes = [source_lines[0]], []
    for line in source_lines[1:]:
        if line.startswith('.model ') and re.search(r'\b(?:adc_bridge|dac_bridge)\(',line):
            continue  # Unused declarations; analog replay has no A instances.
        if line.startswith('.model ') and ' SW(' in line:
            name = line.split()[1]
            if name not in models or line != f'.model {name} SW(RON={models[name][0]} ROFF={models[name][1]} VT=2.5 VH=0)':
                raise ValueError('Unreviewed switch model')
            continue
        if line.startswith('S'):
            fields = line.split()
            if len(fields) != 6 or fields[-1] not in models:
                raise ValueError('Unreviewed switch instance')
            name,p,n,cp,cn,model = fields
            on,off = models[model]
            mapped = f'Bmap_{name} {p} {n} I={{V({p},{n})/(V({cp},{cn})>2.5 ? {on} : {off})}}'
            changes.append({'original':line,'mapped':mapped})
            line = mapped
        if line.startswith('A'):
            raise ValueError('HDL/XSPICE instance remains')
        if line.startswith('.save ') or line.startswith('.options '):
            continue
        if line.startswith('.tran '):
            fields = line.split()
            if len(fields) != 3:
                raise ValueError('Unexpected analysis')
            step,stop = fields[1:]
            continue
        if line.startswith('B') and '{' not in line:
            line = re.sub(r'([VI]=)(.+)$',r'\1{\2}',line)
        lines.append(line)
    if not changes:
        raise ValueError('No switch mapping to audit')
    # Explicit settings, not an assertion of equivalent solver tolerances.
    if engine == 'xyce':
        lines += ['.options device temp=27 tnom=27',
                  '.options timeint method=trap reltol=1e-4 abstol=1e-13',
                  '.options nonlin reltol=1e-4 abstol=1e-13 maxstep=1000',
                  '.options nonlin-tran reltol=1e-4 abstol=1e-13 maxstep=1000',
                  f'.tran {step} {stop} 0 {step}',
                  f'.print tran format=noindex file=host-raw.txt precision=17 {signals[0]}','.end']
    else:
        lines += ['.temp 27','.options tnom=27 reltol=1e-4 vntol=1e-7 abstol=1e-13 itl4=1000 minbreak=1f trtol=1',
                  f'.tran {step} {stop}', '.control','set numdgt=17','set wr_singlescale','set wr_vecnames',
                  'run',f'wrdata host-trace.txt {signals[0]}','quit','.endc','.end']
    return '\n'.join(lines)+'\n', changes, signals[0].split(), float(stop)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path)
    p.add_argument('--engine',choices=['ngspice','xyce'],required=True)
    p.add_argument('--executable',required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args(); source=args.source.resolve(); out=args.out.resolve()
    prior=json.loads((source/'report.json').read_text())
    if (prior.get('completed') is not True or prior.get('omitCaptureKnot') is not True
            or prior.get('effectiveTruncationTolerance') != 1):
        raise ValueError('Expected completed replay with matched trtol and no capture-end knot')
    if sha(source/'io.cir')!=prior['deckSha256']:
        raise ValueError('Source deck changed')
    executable=Path(shutil.which(args.executable) or args.executable).resolve(strict=True)
    env=None
    if args.engine=='ngspice':
        runtime,env=identify(str(executable),prior['ngspiceRuntime']['spinit']['path'])
        if runtime!=prior['ngspiceRuntime']: raise ValueError('Different ngspice runtime')
    else:
        runtime={str(executable):sha(executable)}
        library=executable.parent.parent/'lib/libxyce.dylib'
        if library.exists(): runtime[str(library)]=sha(library)
    text,changes,signals,stop=convert((source/'io.cir').read_text(),args.engine)
    out.mkdir(parents=True,exist_ok=False);(out/'io.cir').write_text(text)
    report={'completed':False,'qualified':False,'engine':args.engine,'runtime':runtime,
            'scope':__doc__,'sourceReportSha256':sha(source/'report.json'),
            'sources':{n:sha(Path(__file__).parent/n) for n in ['independent_driver_replay.py','ngspice_runtime.py','failure_evidence.py']},
            'switchMapping':changes,'stopSeconds':stop,'signals':signals,
            'boundary':'Switch resistance and threshold are preserved away from equality. At exactly 2.5 V the mapped switch is off, whereas ngspice SW can retain state. This mapping requires its ngspice control; time-integration, nonlinear tolerances and device implementations differ across solvers. Short constructed stimulus only, not firmware or physical qualification.'}
    try:
        command=[str(executable),'-n','-b','io.cir'] if args.engine=='ngspice' else [str(executable),'io.cir']
        with (out/'solver.log').open('w') as log:
            result=subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=600)
        report['exitCode']=result.returncode
        log=(out/'solver.log').read_text()
        if args.engine=='ngspice':
            verify(runtime);diagnostic=solver_diagnostic(log)
        else:
            for path,digest in runtime.items():
                if sha(Path(path))!=digest: raise ValueError('Runtime changed')
            diagnostic=bool(re.search(r'\b(?:warning|error|fatal)\b',log,re.I))
        report['solverDiagnostic']=diagnostic
        if result.returncode or diagnostic: raise ValueError('Solver diagnostic; inspect log')
        if args.engine=='xyce':
            lines=(out/'host-raw.txt').read_text().splitlines()
            if lines[0].split()!=['TIME',*[s.upper() for s in signals]] or lines[-1]!='End of Xyce(TM) Simulation':
                raise ValueError('Unexpected Xyce trace layout')
            (out/'host-trace.txt').write_text('time '+' '.join(signals)+'\n'+'\n'.join(lines[1:-1])+'\n')
        from host_waveform_comparison import rows
        samples=list(rows(out/'host-trace.txt',signals,float('inf')))
        if not samples or abs(samples[-1][0]-stop)>1e-15: raise ValueError('Incomplete trace')
        report.update(completed=True,rows=len(samples),lastSampleSeconds=samples[-1][0])
    except Exception as error:
        report['error']=str(error)
        raise
    finally:
        report['artifacts']={n:sha(out/n) for n in ['io.cir','solver.log','host-trace.txt','host-raw.txt'] if (out/n).exists()}
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(out/'report.json')


if __name__=='__main__':main()
