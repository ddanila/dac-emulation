#!/usr/bin/env python3
"""Capture matched ngspice refinements without storing complete raw waveforms."""
import argparse
import json
import math
from pathlib import Path
import re
from audit_log import records
from compare_firmware_io import sha
from eval_cache_benchmark import external_dependencies, verify_dependencies
from full_scenario_refinement import same_events
from io_scenario import load, observe
from live_raw_review import signal_name
from ngspice_runtime import identify, verify
from scenario_capture import endpoint_ns, validate_stimulus
from serial_observation import validate_transport
from stream_capture import run


def capture(decks,out,executable,spinit,timeout,inputs,environment,scenario_path=None,log_limits=None):
    if len(decks)!=3 or not math.isfinite(timeout) or timeout<=0:raise ValueError('Need three levels and a finite positive timeout')
    decks=[p.resolve() for p in decks];out=out.resolve()
    texts=[p.read_text() for p in decks]
    if any(re.search(r'^\s*\.(include|lib)\b',t,re.M|re.I) for t in texts):raise ValueError('Use a self-contained deck with pinned inputs')
    pattern=r'^\.tran ([0-9.eE+-]+)n ([0-9.eE+-]+)n\s*$'
    settings=[re.findall(pattern,t,re.M) for t in texts]
    if any(len(v)!=1 for v in settings):raise ValueError('Expected explicit nanosecond timestep and endpoint')
    steps=[float(v[0][0]) for v in settings];ends=[float(v[0][1]) for v in settings]
    if not all(math.isfinite(v) and v>0 for v in steps+ends) or steps[0]!=2*steps[1] or steps[1]!=2*steps[2] or len(set(ends))!=1:
        raise ValueError('Need two successive halvings and one complete endpoint')
    normalized=[re.sub(pattern,r'.tran STEP \2n',t,flags=re.M) for t in texts]
    if any(t!=normalized[0] for t in normalized):raise ValueError('Circuit differs beyond timestep')
    for text in texts:
        if len(re.findall(r'^run waveform\.raw$',text,re.M))!=1 or re.search(r'^\s*(wrdata|write|resume|stop|source|shell)\b',text,re.M|re.I):
            raise ValueError('Need one direct raw producer without other output or execution commands')
    saves=re.findall(r'^\.save (.+)$',texts[0],re.M)
    if len(saves)!=1:raise ValueError('Need explicit saved observation scope')
    expected={signal_name(n) for n in saves[0].split()}
    if len(expected)!=len(saves[0].split()):raise ValueError('Ambiguous saved scope')
    if any(Path(n).is_absolute() or '..' in Path(n).parts for n in inputs):raise ValueError('Inputs must be local relative paths')
    fingerprints=[{n:sha(p.parent/n) for n in inputs} for p in decks]
    if any(v!=fingerprints[0] for v in fingerprints):raise ValueError('Different producer inputs')
    dependencies=[external_dependencies(p.parent,{'deck':p.name,'inputs':inputs}) for p in decks]
    if any(v!=dependencies[0] for v in dependencies):raise ValueError('Different runtime libraries')
    runtime,env=identify(str(executable),str(spinit))
    for key in list(env):
        if key.startswith('ROBOTRON_'):del env[key]
    if any(not k.startswith('ROBOTRON_') or not isinstance(v,str) for k,v in environment.items()):raise ValueError('Unexpected experimental environment')
    env.update(environment)
    scenario_hash=sha(scenario_path) if scenario_path else None
    scenario=load(scenario_path) if scenario_path else None
    if scenario:
        if not {'io.vvp','s600.hex'}<=set(inputs):raise ValueError('Scenario requires pinned HDL and ROM inputs')
        for text in texts:
            validate_stimulus(text,scenario);endpoint_ns(text,scenario,ends[0])
    original_hashes=[sha(p) for p in decks]
    prepared=[]
    def builder(index):
        def command(fd):
            # Only the output destination changes. Inherited descriptors make
            # EOF observable even if ngspice fails before opening the raw file.
            path=out/f'{index}.cir'
            path.write_text(texts[index].replace('\nrun waveform.raw\n',f'\nrun /dev/fd/{fd}\n'))
            prepared.append({'path':str(path),'sha256':sha(path),'rawDescriptor':fd})
            return [runtime['executable']['path'],'-n','-b',str(path)],decks[index].parent
        return command
    transport=run([builder(i) for i in range(3)],out,env,ends[0]*1e-9,timeout,**(log_limits or {}))
    verify(runtime);verify_dependencies(dependencies[0])
    if scenario_path and sha(scenario_path)!=scenario_hash:raise ValueError('Scenario changed during capture')
    if any(sha(Path(r['path']))!=r['sha256'] for r in prepared):raise ValueError('Executed deck changed during capture')
    if [sha(p) for p in decks]!=original_hashes or any({n:sha(p.parent/n) for n in inputs}!=fingerprints[0] for p in decks):
        raise ValueError('Inputs changed during capture')
    comparisons=transport['comparisons']
    if any(set(c['signals'])!=expected for c in comparisons):raise ValueError('Missing saved observations')
    previous,finest=[c['signals'] for c in comparisons]
    failures={name:{'previous':previous[name]['maximumAbsoluteDifference'],'finest':v['maximumAbsoluteDifference']}
              for name,v in finest.items() if v['unit']=='V' and (v['maximumAbsoluteDifference']>.01 or v['maximumAbsoluteDifference']>previous[name]['maximumAbsoluteDifference'])}
    coverage=[];event_count=None
    if scenario:
        event_count=same_events([out/f'{i}.log' for i in range(3)])
        for i in range(3):
            serial='\n'.join(records(out/f'{i}.log',('SERIAL_',)))
            observed=validate_transport(serial,require_activity=any(w['minimumBits'] for w in scenario['observations']))
            for key in ('transmitted','received'):
                if any(stamp*1e-12>ends[0]*1e-9 for stamp,_ in observed[key]):raise ValueError('Serial event outside window')
            coverage.append({key:observe(scenario,observed[key],electrical=True) for key in ('transmitted','received')})
    receipt={'runtime':runtime,'externalDependencies':dependencies[0],'environment':environment,
             'sourceDecks':[{'path':str(p),'sha256':h} for p,h in zip(decks,original_hashes)],'preparedDecks':prepared,
             'inputs':fingerprints[0],'stepsNs':steps,'endNs':ends[0],
             'scenario':{'path':str(scenario_path),'sha256':scenario_hash} if scenario else None,
             'sources':{n:sha(Path(__file__).parent/n) for n in ('stream_refinement_capture.py','stream_capture.py','raw_stream_review.py')},
             'transport':transport,'voltageGatePassed':not failures,'voltageFailures':failures,
             'firmwareEventRecordsCompared':event_count,'serialCoverage':coverage,
             'serialWindowsPassed':all(v['passed'] for c in coverage for v in c.values()) if scenario else None,
             'qualified':False,'boundary':'Complete live three-level online comparison. Full scenario claims require explicit stimulus and serial-window checks; matched disabled controls, coupled rollback and physical-model admission remain separate. Complete raw bytes are hashed, not retained for later waveform replay.'}
    (out/'assessment.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--decks',type=Path,nargs=3,required=True)
    for n in ('out','runtime','spinit','environment'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--input',action='append',default=[]);p.add_argument('--scenario',type=Path)
    p.add_argument('--timeout',type=float,required=True)
    p.add_argument('--max-log-bytes',type=int,default=1024**3)
    p.add_argument('--max-compressed-log-bytes',type=int,default=256*1024**2)
    p.add_argument('--max-log-line-bytes',type=int,default=1024**2)
    a=p.parse_args()
    capture(a.decks,a.out,a.runtime,a.spinit,a.timeout,a.input,json.loads(a.environment.read_text()),a.scenario,{k:getattr(a,k) for k in ('max_log_bytes','max_compressed_log_bytes','max_log_line_bytes')})
