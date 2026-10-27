#!/usr/bin/env python3
"""Native scope metadata mutation, restoration and zero-output refusal controls."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
CHANGES='units precision file line deffile defline cell name definition omit order time stime realtime'.split()
REFUSALS='time stime realtime classes root intern parent missing-child'.split()
EXPECTED=[]
for round_id in (1,2):
    EXPECTED += [f'ROUND {round_id}', *['CHANGED '+x for x in CHANGES], *['REFUSED '+x for x in REFUSALS],f'RESTORED {round_id}']
EXPECTED += ['CONTINUE 5 2','finish']


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native scope metadata control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();events=[];i=0
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and not lines[i].startswith('VSM_END '):i+=1
                if i==len(lines) or mode!='enabled' or key in images:raise ValueError('Invalid scope metadata image')
                i+=1;images[key]=lines[start:i];continue
            events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=EXPECTED:raise ValueError('Changed native continuation: '+str(events))
    for mode in ('baseline','disabled','enabled'):
        key='unsupported-'+mode
        if receipt['runs'][key]['exitCode'] or (root/(key+'.stderr')).read_text():raise ValueError('Failed automatic control')
        lines=(root/(key+'.stdout')).read_text().splitlines()
        if len(lines)!=3 or lines[:2]!=['REFUSED automatic','CONTINUE automatic'] or '$finish called at 1000 (1ps)' not in lines[2]:raise ValueError('Changed automatic continuation')
    if set(images)!={f'{kind}{i}' for i in (1,2) for kind in ['before','restored',*CHANGES]}:raise ValueError('Missing metadata witnesses')
    for i in (1,2):
        before=images[f'before{i}']
        if before!=images[f'restored{i}'] or before[0]!=f'VSM_BEGIN 1 {i*1000}':raise ValueError('Changed restoration/time binding')
        if not any(l.startswith('VSM_FUNCTION ') for l in before):raise ValueError('Missing function metadata')
        for kind in CHANGES:
            after=images[f'{kind}{i}']
            prefix='VSM_SCOPE' if kind in CHANGES[:7] else ('VSM_NAME' if kind=='name' else 'VSM_DEFINITION' if kind=='definition' else 'VSM_INTERN' if kind=='omit' else 'VSM_OBJECT' if kind=='order' else 'VSM_TIME')
            if [l for l in before if l.startswith(prefix+' ')]==[l for l in after if l.startswith(prefix+' ')]:raise ValueError('Missing field witness: '+kind)
            if after==before or after[0]!=before[0] or after[-1]!=before[-1]:raise ValueError('Missing metadata distinction: '+kind)
    return dict(qualified=False,controlsPassed=True,originalContinuationExactlyEqual=True,
        automaticScopeZeroOutputRefusal=True,changedFields=CHANGES,zeroOutputRefusals=REFUSALS,rounds=2,
        scope='Static native scope metadata and ordered internal-object identities/types. Fourteen mutations and eight zero-output refusals per round, exact restoration and original HDL continuation. Function metadata is observed, not mutated. No intern payload coverage, deletion/address reuse, unsupported scope family or operational board qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_metadata.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    shutil.copy2(HERE/'fixtures/scope_metadata_unsupported.v',out/'unsupported.v')
    commands.append(['iverilog','-g2012','-o',str(out/'unsupported.vvp'),str(out/'unsupported.v')])
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',out/'unsupported.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_SCOPE_METADATA='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
        key='unsupported-'+mode;cmd=cmd[:-1]+['unsupported.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(key+'.stdout')).write_text(r.stdout);(out/(key+'.stderr')).write_text(r.stderr)
        runs[key]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
