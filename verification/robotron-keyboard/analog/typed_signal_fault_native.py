#!/usr/bin/env python3
"""Replay paired metadata fault APIs with native callback continuation."""
import argparse,copy,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
import callback_signal_links as prior
from signal_handles import parse as signal_parse
from callback_list_probe import parse as list_parse
from net_probe import parse as graph_parse
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def parse_state(lines):
    i=0;state={}
    for key,prefix,parser in [('links','VSL',prior.parse),('signals','VSH',signal_parse),('lists','VCL',list_parse),('graph','VNG',graph_parse)]:
        start=i
        while i<len(lines) and not lines[i].startswith(prefix+'_END '):i+=1
        if i==len(lines):raise ValueError('Incomplete native metadata snapshot')
        i+=1;state[key]=parser(lines[start:i])
    if i!=len(lines):raise ValueError('Unexpected native metadata records')
    prior.validate(state);return state


def review(root):
    states={};guards=[];refusals=[];active=0
    # Strip only this extension's records, then replay the unchanged native
    # callback/link continuation oracle against every original control.
    with tempfile.TemporaryDirectory() as tmp:
        filtered=Path(tmp);shutil.copy2(root/'run.json',filtered/'run.json')
        for mode in ('baseline','disabled','enabled'):
            lines=(root/(mode+'.stdout')).read_text().splitlines();output=[];i=0
            while i<len(lines):
                line=lines[i];i+=1
                if line.startswith('STATE '):
                    start=i
                    while i<len(lines) and lines[i]!='END_STATE':i+=1
                    if i==len(lines):raise ValueError('Incomplete native state')
                    name=line.split()[1];body=lines[start:i];i+=1
                    if name.startswith('typed-') or name=='restored':
                        if mode!='enabled' or name in states:raise ValueError('Duplicate/disabled typed snapshot')
                        states[name]=parse_state(body)
                    if not name.startswith('typed-'):output.extend([line,*body,'END_STATE'])
                    continue
                if line.startswith(('TYPED_','REFUSED typed-')):
                    if mode!='enabled':raise ValueError('Fault API active in original/disabled control')
                    if line.startswith('TYPED_GUARD '):guards.append(int(line.split()[1]))
                    elif line=='TYPED_ACTIVE_REFUSED':active+=1
                    elif line.startswith('REFUSED typed-'):refusals.append(int(line.rsplit('-',1)[1]))
                    else:raise ValueError('Unknown typed metadata record')
                    continue
                output.append(line)
            (filtered/(mode+'.stdout')).write_text('\n'.join(output)+'\n');shutil.copy2(root/(mode+'.stderr'),filtered/(mode+'.stderr'))
        previous=prior.review(filtered)
    if guards!=list(range(6)) or refusals!=list(range(2,6)) or active!=3:raise ValueError('Incomplete paired fault guards or active refusal')
    if set(states)!={'restored','typed-0','typed-1',*[f'typed-restored-{i}' for i in range(6)]}:raise ValueError('Missing native metadata fault snapshots')
    base=states['restored']
    for field in range(6):
        if states[f'typed-restored-{field}']!=base:raise ValueError('Native metadata fault did not restore')
    for field in (0,1):
        expected=copy.deepcopy(base)
        target=next(r for r in expected['signals']['rows'] if bytes.fromhex(r['name'])==b'a\0')
        target['signed' if field==0 else 'msb']^=1
        if states[f'typed-{field}']!=expected:raise ValueError('Wrong native metadata mutation')
    return dict(qualified=False,controlsPassed=True,priorCallbackControls=previous,originalContinuationExactlyEqual=True,
                scope='All six paired metadata fault APIs restore exact native signal/callback/graph state. Wrong field or handle restoration attempts refuse without losing the pending fault, and mutation during active callback traversal refuses. Original and instrumented callback/value continuation agrees. Combined startup faults and operational campaign qualification remain separate.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/typed_signal_faults.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_REFERENTS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
