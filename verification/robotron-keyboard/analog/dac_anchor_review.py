#!/usr/bin/env python3
"""Retain short live controls for opt-in event-anchored DAC arithmetic."""
import argparse,json,lzma,shutil
from decimal import Decimal as D, localcontext
from pathlib import Path
from compare_firmware_io import sha
from host_waveform_comparison import rows
from dac_partition_review import exact_ramp

HERE=Path(__file__).resolve().parent

def retain(root,out,build):
    out.mkdir(parents=True,exist_ok=False);cases={};receipts={}
    for name in ('disabled','25','12.5','6.25'):
        src=root/('dac-anchored-prefix-'+name);dst=out/name;dst.mkdir()
        run=json.loads((src/'run.json').read_text());receipts[name]=run
        if run['timedOut'] or run['exitCode']!=0 or run['haltNs']!=12 or run['stopNs']!=1006000 or run['dacAnchored']!=(name!='disabled'):
            raise ValueError('Unexpected candidate control')
        if sha(src/'io.cir')!=run['deckSha256']:raise ValueError('Changed deck')
        for file,digest in run['inputs'].items():
            if sha(src/file)!=digest:raise ValueError('Changed stimulus')
        if sha(src/'sampling-grid.json')!=run['samplingGridSha256']:raise ValueError('Changed grid')
        for file in ('io.cir','run.json','sampling-grid.json'):shutil.copyfile(src/file,dst/file)
        for file in ['ngspice.log']+[p.name for p in src.glob('*.txt')]:
            with lzma.open(dst/(file+'.xz'),'wb') as f:f.write((src/file).read_bytes())
        column=run['observationSignals'].index('v(wr_high)')+1
        samples=list(rows(src/'network_witness.txt',run['observationSignals'],run['stepNs']))
        worst={'absoluteVolts':'0'};mismatches=0
        for sample in samples:
            t=sample[0];value=sample[column]
            expected=max(0.,min(5.,5e9*(t-1e-8)))
            mismatches+=value!=expected
            with localcontext() as c:
                c.prec=64;error=abs(D.from_float(value)-exact_ramp(t))
            if error>D(worst['absoluteVolts']):worst={'absoluteVolts':str(error),'timeSeconds':t,'capturedVolts':value}
        if name!='disabled' and mismatches:raise ValueError('Anchored ramp differs from declared equation')
        cases[name]={'traceSha256':{p.name:sha(p) for p in src.glob('*.txt')},'endSeconds':samples[-1][0],
                     'samples':len(samples),'doubleEquationMismatches':mismatches,'maximumExactRampError':worst}
    ignored={'elapsedSeconds','dacAnchored','stepNs','samplingGridSha256','deckSha256'}
    base={k:v for k,v in receipts['disabled'].items() if k not in ignored}
    for run in receipts.values():
        if {k:v for k,v in run.items() if k not in ignored}!=base:raise ValueError('Unmatched controls')
    original=HERE/'reports/dac-state-startup/original'
    if any(sha(original/name)!=digest for name,digest in cases['disabled']['traceSha256'].items()):
        raise ValueError('Disabled candidate changes original capture')
    shutil.copyfile(build,out/'build.json')
    result={'schema':1,'cases':cases,'disabledCaptureMatchesOriginal':True,'qualified':False,
        'scope':'Short live startup diagnostic, not full-window convergence. Every enabled saved wr_high value matches the event-anchored binary64 ramp equation; exact-ramp error uses 64-digit arithmetic. Endpoints differ near the diagnostic halt, so no pairwise full-window gate is claimed. Compiled helper tests cover interrupted ramps and discarded trial isolation; full coupled rollback and firmware scenarios remain required. Candidate remains opt-in.',
        'sources':{n:sha(HERE/n) for n in ('dac_anchor_review.py','dac_partition_review.py','live_transition_probe.py','build_live_transition_models.py','engine-patches/dac_anchor.h','engine-patches/dac-anchored-ramp.patch','test_dac_anchor.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v['maximumExactRampError'] for k,v in cases.items()},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();retain(a.runs,a.out,a.build)
