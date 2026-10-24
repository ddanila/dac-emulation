#!/usr/bin/env python3
"""Retain bounded DAC instrumentation controls and internal time-history evidence."""
import argparse,json,lzma,re,shutil
from pathlib import Path
from compare_firmware_io import sha
from host_waveform_comparison import rows
from trace_io import open_text

HERE=Path(__file__).resolve().parent

def retain(root,out,build):
    out.mkdir(parents=True,exist_ok=False)
    cases={};data={}
    for name in ('original','disabled','enabled','12.5','6.25'):
        src=root/('dac-state-prefix-'+name);dst=out/name;dst.mkdir()
        run=json.loads((src/'run.json').read_text())
        if run['exitCode']!=0 or run['timedOut'] or run['haltNs']!=12 or run['stopNs']!=1006000:
            raise ValueError('Invalid diagnostic receipt')
        if run['dacStateAudit']!=(name in ('enabled','12.5','6.25')):raise ValueError('Unexpected audit flag')
        if sha(src/'io.cir')!=run['deckSha256']:raise ValueError('Changed deck')
        for file,digest in run['inputs'].items():
            if sha(src/file)!=digest:raise ValueError('Changed runtime input')
        for file in ('run.json','io.cir','sampling-grid.json'):shutil.copyfile(src/file,dst/file)
        log=(src/'ngspice.log').read_text()
        with lzma.open(dst/'ngspice.log.xz','wt') as f:f.write(log)
        for raw in src.glob('*.txt'):
            with lzma.open(dst/(raw.name+'.xz'),'wb') as f:f.write(raw.read_bytes())
        samples=list(rows(src/'network_witness.txt',run['observationSignals'],run['stepNs']))
        column=run['observationSignals'].index('v(wr_high)')+1
        prior={b[0]:a for a,b in zip(samples,samples[1:])};saved={s[0]:s for s in samples}
        mismatches={};calls=0
        for line in log.splitlines():
            if 'DAC_STATE time=' not in line:continue
            fields=dict(re.findall(r'(\w+)=([^ ]+)',line))
            q={k:(int(v) if k in ('old','current') else float.fromhex(v)) for k,v in fields.items()};calls+=1
            t=q['time']
            if 1e-8<t<11e-9 and t in prior and q['previous_time']!=prior[t][0]:
                if q['old']!=1 or q['current']!=1:raise ValueError('Unexpected ramp state')
                predicted=q['previous_value']+5e9*(t-q['previous_time'])
                if predicted!=q['value'] or saved[t][column]!=q['value']:raise ValueError('Ramp equation does not reproduce capture')
                mismatches[t]={**q,'previousSavedTime':prior[t][0],
                    'previousSavedValue':prior[t][column],
                    'timeDifferenceSeconds':q['previous_time']-prior[t][0],
                    'incrementDifferenceVolts':q['value']-(q['previous_value']+5e9*(t-prior[t][0]))}
        step='25' if name in ('original','disabled','enabled') else name
        full=root/('nested-local-full-'+step)/'network_witness.txt'
        endpoint=json.loads((HERE/'reports/nested-local-refinement'/step/'trace-endpoints.json').read_text())['network_witness.txt']
        if sha(full)!=endpoint['sha256']:raise ValueError('Changed full capture')
        matched=0;last=0
        with open_text(full) as a,open_text(src/'network_witness.txt') as b:
            if next(a)!=next(b):raise ValueError('Header differs')
            for x,y in zip(a,b):
                if x!=y:break
                matched+=1;last=float(x.split()[0])
        if last<11e-9:raise ValueError('Halt changed the ramp under investigation')
        cases[name]={'traceSha256':{p.name:sha(p) for p in src.glob('*.txt')},
            'fullCaptureSha256':endpoint['sha256'],'identicalFullPrefixRows':matched,'identicalFullPrefixThroughSeconds':last,
            'auditCalls':calls,'rampTimeHistoryDifferences':list(mismatches.values())}
        data[name]=src
    for n in ('disabled','enabled'):
        if cases[n]['traceSha256']!=cases['original']['traceSha256']:raise ValueError('Instrumentation changes capture')
        if (data[n]/'io.cir').read_bytes()!=(data['original']/'io.cir').read_bytes():raise ValueError('Unmatched control decks')
    shutil.copyfile(build,out/'build.json')
    result={'schema':1,'cases':cases,'instrumentationControlsIdentical':True,'qualified':False,
        'scope':'Diagnostic halt retains the full transient horizon. Prefix bytes match each original full capture through the complete 10–11 ns DAC ramp, but may diverge near the halt. Three coarse instrumentation controls are byte-identical. Logged prior-time rounding differs from saved prior timestamps; the unchanged DAC ramp equation reproduces the corresponding accepted values. This identifies arithmetic history, not physical error, and does not waive any whole-window convergence gate.',
        'sources':{n:sha(HERE/n) for n in ('dac_state_review.py','diagnostic_halt.py','live_transition_probe.py','build_live_transition_models.py','engine-patches/dac-state-audit.patch')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({k:v['rampTimeHistoryDifferences'] for k,v in cases.items()},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--build',type=Path,required=True);a=p.parse_args();retain(a.runs,a.out,a.build)
