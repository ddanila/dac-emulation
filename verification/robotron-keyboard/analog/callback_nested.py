#!/usr/bin/env python3
"""Native nested value dispatch and complete-list observation guards."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from callback_list_probe import parse
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def review(root):
    receipt=json.loads((root/'run.json').read_text());observations=refusals=0
    # The native VPI formatter uses shared RBUF_VAL storage. Nested A=3
    # overwrites the vector result visible to suspended B and outer A, even
    # though b itself remains 2. Preserve this original-runtime behavior.
    base=['S0','ENTER 2000 A 1 1 0','ENTER 2000 B 2 2 0','ENTER 2000 A 3 3 0',
          'EXIT 2000 A 3 3 0','EXIT 2000 B 2 3 0','EXIT 2000 A 1 3 0','S1','VALUES 2000 3 2',
          'ENTER 4000 A 1 4 0','EXIT 4000 A 1 4 0','S2','VALUES 4000 4 2',
          'ENTER 6000 B 1 5 0','EXIT 6000 B 1 5 0','S3','VALUES 6000 4 5','finish']
    enabled=[]
    for line in base:
        if line.startswith('EXIT '):enabled.append('NEST_REFUSED exit '+line.split()[3])
        enabled.append(line)
        if line.startswith('ENTER '):enabled.append('NEST_REFUSED enter '+line.split()[3])
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native nested callback failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=0;events=[];layout=None
        def consume(wanted):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=wanted:raise ValueError('Expected '+wanted)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(lines) and not lines[cursor].startswith('VCL_END '):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated nested callback image')
            cursor+=1;return parse(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if not line.startswith('NEST_STAGE '):
                events.append('finish' if '$finish called at 7000 (1ps)' in line else ' '.join(line.split()));cursor+=1;continue
            consume(f'NEST_STAGE {stage}');events.append(f'S{stage}')
            if stage>=4:raise ValueError('Extra nested callback stage')
            if mode=='enabled':
                consume('NEST_BEFORE');before=snapshot();consume('NEST_REPEAT')
                if snapshot()!=before or before['tick']!=(1000,2000,4000,6000)[stage]:raise ValueError('Changed nested observation/time')
                if layout is None:
                    layout=before['owners'];populated=[o for o in layout if o['callbacks']]
                    if len(populated)!=2 or any(len(o['callbacks'])!=1 or o['words'] for o in layout):raise ValueError('Wrong nested owner membership')
                    a,b=[o['callbacks'][0] for o in populated]
                    if a['function']!=b['function'] or not a['function'] or not a['object'] or not b['object'] or a['object']==b['object'] or b['user']!=a['user']+1:raise ValueError('Wrong nested callback bindings')
                if before['owners']!=layout:raise ValueError('Nested traversal changed callback/owner identity')
                observations+=1
            consume(f'NEST_DONE {stage}');stage+=1
        if stage!=4 or events!=(enabled if mode=='enabled' else base):raise ValueError('Changed nested dispatch, shared result or guard lifetime: '+repr(events))
        refusals+=sum(e.startswith('NEST_REFUSED ') for e in events)
    return dict(qualified=False,controlsPassed=True,observations=observations,activeTraversalRefusals=refusals,maximumNativeDepth=3,originalContinuationExactlyEqual=True,scope='Native no-delay VPI writes nest cross-owner and same-owner callbacks. Complete-list inventory refuses at entry and exit at every depth, including outer callbacks after nested return, and resumes only after complete unwinding. Stable owner/list identities survive the traversal. Exact entry/exit order and shared vector-result overwriting agree with original execution; final HDL signal values remain independently checked.',notEstablished=['Capturing or restoring suspended native traversal and shared VPI result storage','Array-association lifecycle, typed bridge referents and operational integration','General rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/callback_nested.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on')]:
        env=dict(os.environ,K7658_CALLBACK_LISTS=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('callback_nested.py','callback_list_probe.py','net_probe.py','net_types_probe.py','fixtures/callback_nested.c','fixtures/callback_nested.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Native nested callback controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need all runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
