#!/usr/bin/env python3
"""Compare matched startup-grid controls within a predeclared diagnostic window."""
import argparse,json,lzma,math,re,shutil
from pathlib import Path
from compare_firmware_io import sha
from host_waveform_comparison import rows,compare_samples
from local_refinement_grid import startup_grids
from numerical_voltage_budget import voltage_gate
from reset_release_driver_review import trace_summary,TRACES,completed
from network_refinement_review import events
from trace_io import open_text
from live_transition_review import diagnostic
HERE=Path(__file__).resolve().parent
STEPS=('25','12.5','6.25')
WINDOW=1.9e-6

def prefix(samples,stop):
    if not math.isfinite(stop) or stop<=0:raise ValueError('Invalid diagnostic window')
    previous=None
    for row in samples:
        if previous is None and row[0]!=0:raise ValueError('Missing time-zero sample')
        if row[0]<=stop:
            yield row
            if row[0]==stop:return
        else:
            ratio=(stop-previous[0])/(row[0]-previous[0])
            yield (stop,*(x+ratio*(y-x) for x,y in zip(previous[1:],row[1:])))
            return
        previous=row
    raise ValueError('Incomplete diagnostic window')

def retain(root,out):
    out.mkdir(parents=True,exist_ok=False);runs={};cases={};grids={};decks=set();identity=None
    for mode,stem in [('baseline','dac-anchored-startup2us-'),('dense','dense-startup2us-')]:
        runs[mode]={};cases[mode]={};grids[mode]={}
        for step in STEPS:
            src=root/(stem+step);dst=out/mode/step;dst.mkdir(parents=True)
            run=json.loads((src/'run.json').read_text());runs[mode][step]=run
            if run['exitCode']!=0 or run['timedOut'] or run['haltNs']!=2000 or run['stopNs']!=1006000 or not run['dacAnchored'] or run['stepNs']!=float(step):raise ValueError('Unexpected startup control')
            fields={k:v for k,v in run.items() if k not in ('elapsedSeconds','stepNs','deckSha256','samplingGridSha256')}
            if identity is None:identity=fields
            if fields!=identity:raise ValueError('Unmatched runtime, stimulus or numerical settings')
            deck=(src/'io.cir').read_text()
            if sha(src/'io.cir')!=run['deckSha256']:raise ValueError('Changed deck')
            for name,digest in run['inputs'].items():
                if sha(src/name)!=digest:raise ValueError('Changed input')
            stripped,count=re.subn(r'^Vsampling_grid sampling_grid 0 PWL\(0 0\n(?:\+ [^\n]*\n)*?\+ \)\n','<grid>\n',deck,flags=re.M)
            if count!=1:raise ValueError('Unexpected sampling source')
            decks.add(re.sub(r'^\.tran\s+\S+','.tran <step>',stripped,flags=re.M))
            if sha(src/'sampling-grid.json')!=run['samplingGridSha256']:raise ValueError('Changed grid')
            grids[mode][step]=json.loads((src/'sampling-grid.json').read_text())
            log=(src/'ngspice.log').read_text()
            if 'condition met: stop' not in log or diagnostic(log):raise ValueError('Diagnostic capture did not halt cleanly')
            traces={n:trace_summary(src/n) for n in TRACES}
            if not all(t['firstSeconds']==0 and t['strictlyIncreasing'] and 2e-6<=t['lastSeconds']<=2e-6+float(step)*1e-9 for t in traces.values()):raise ValueError('Incomplete diagnostic capture')
            for name in ('io.cir','run.json','sampling-grid.json'):shutil.copyfile(src/name,dst/name)
            for name in ('ngspice.log','network_witness.txt'):
                with lzma.open(dst/(name+'.xz'),'wb') as f:f.write((src/name).read_bytes())
            (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
            cases[mode][step]={'completedDiagnosticPrefix':True,'traceSha256':traces['network_witness.txt']['sha256'],'requestedPoints':len(grids[mode][step]['timesSeconds'])}
    if len(decks)!=1:raise ValueError('Physical decks differ beyond step and isolated grid')
    expected=startup_grids([grids['baseline'][s] for s in STEPS],2000)
    for step,grid in zip(STEPS,expected):
        for key in ('timesSeconds','startupWindowNs','startupStepNs','localStepNs','stopNs','peakHalfWindowNs'):
            if grids['dense'][step].get(key)!=grid[key]:raise ValueError('Unexpected startup-grid extension')
    failed=[]
    attempt=root/'dense-startup2us-6.25-timeout'
    if attempt.exists():
        run=json.loads((attempt/'run.json').read_text())
        if not run['timedOut']:raise ValueError('Expected terminal timeout control')
        if (attempt/'io.cir').read_bytes()!=(root/'dense-startup2us-6.25/io.cir').read_bytes():raise ValueError('Retry changed its deck')
        dst=out/'timeout-control';dst.mkdir()
        for name in ('run.json','io.cir','sampling-grid.json'):shutil.copyfile(attempt/name,dst/name)
        with lzma.open(dst/'ngspice.log.xz','wb') as f:f.write((attempt/'ngspice.log').read_bytes())
        failed.append({'path':'timeout-control','timedOut':True,'waveformRetained':False,'countsForConvergence':False})
    full=root/'dac-anchored-full-25';run=json.loads((full/'run.json').read_text());log=(full/'ngspice.log').read_text()
    traces={n:trace_summary(full/n) for n in TRACES}
    if not completed(run,traces,diagnostic(log)):raise ValueError('Incomplete full coarse control')
    if sha(full/'io.cir')!=run['deckSha256']:raise ValueError('Changed full deck')
    prefix_deck=(root/'dac-anchored-startup2us-25/io.cir').read_text()
    if re.sub(r'^stop when time > .*\n','',prefix_deck,flags=re.M)!=(full/'io.cir').read_text():raise ValueError('Prefix differs beyond diagnostic halt')
    baseline=runs['baseline']['25']
    ignored={'elapsedSeconds','deckSha256','haltNs'}
    if {k:v for k,v in run.items() if k not in ignored}!={k:v for k,v in baseline.items() if k not in ignored}:raise ValueError('Full-prefix controls differ')
    through=0
    with open_text(full/'network_witness.txt') as a,open_text(root/'dac-anchored-startup2us-25/network_witness.txt') as b:
        if next(a)!=next(b):raise ValueError('Prefix header mismatch')
        for x,y in zip(a,b):
            if x!=y:break
            through=float(x.split()[0])
    if through<WINDOW:raise ValueError('Diagnostic halt changes comparison window')
    dst=out/'baseline-full-25';dst.mkdir()
    for name in ('run.json','io.cir','sampling-grid.json'):shutil.copyfile(full/name,dst/name)
    with lzma.open(dst/'ngspice.log.xz','wb') as f:f.write(log.encode())
    (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
    full_summary={'completed':True,'diagnosticPrefixMatchesThroughSeconds':through,'bus':events(log),'qualified':False}
    comparisons={}
    for mode in runs:
        pairs=[]
        for a,b in zip(STEPS,STEPS[1:]):
            signals=runs[mode][a]['observationSignals']
            result=compare_samples(*(prefix(rows(out/mode/s/'network_witness.txt',signals,float(s)),WINDOW) for s in (a,b)))
            pairs.append({'coarse':a,'fine':b,'endSeconds':result['endSeconds'],'signals':{n:{'unit':'V' if n.lower().startswith('v(') else 'A','maximumAbsoluteDifference':v['maximumDifferenceV'],'timeSeconds':v['timeSeconds']} for n,v in zip(signals,result['signals'])}})
        comparisons[mode]={'pairs':pairs,'diagnosticVoltageGate':voltage_gate(pairs)}
    result={'schema':1,'windowSeconds':[0,WINDOW],'haltSeconds':2e-6,'declaredHorizonSeconds':.001006,'cases':cases,'failedControls':failed,'baselineFullPrefix':full_summary,'comparisons':comparisons,'qualified':False,
        'scope':'Matched startup-only screen with a predeclared 0–1.9 us comparison window before the 2 us diagnostic halt. Endpoints use ordinary linear interpolation at the shared boundary. The full transient horizon and physical circuit remain fixed. Diagnostic results do not substitute for the complete reset-release or full-repeat gate; no acceptance threshold is changed.',
        'sources':{n:sha(HERE/n) for n in ('startup_grid_review.py','local_refinement_grid.py','live_transition_probe.py','host_waveform_comparison.py','numerical_voltage_budget.py','trace_io.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    manifest={str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()};(out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    for mode,c in comparisons.items():print(mode,c['diagnosticVoltageGate']['passed'],{n:v for n,v in c['diagnosticVoltageGate']['nodes'].items() if not v['nonIncreasing']})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();retain(a.runs,a.out)
