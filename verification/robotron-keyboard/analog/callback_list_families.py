#!/usr/bin/env python3
"""Exercise native stateful callback and unknown-owner refusal lifecycles."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from callback_list_probe import parse
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
FAMILIES={'part':'a[2:1]','word':'mem[0]','array-part':'mem[0][2:1]','array':'mem','owner':'a'}

def review(root):
    receipt=json.loads((root/'run.json').read_text());refused=admitted=0
    for family in FAMILIES:
        for timing in ('early','late'):
            reference=None
            for mode in ('original','disabled','observe'):
                name=f'{family}-{timing}-{mode}'
                if receipt['runs'][name]['exitCode'] or (root/(name+'.stderr')).read_text():raise ValueError('Failed native family control')
                lines=(root/(name+'.stdout')).read_text().splitlines();cursor=stage=0;ordinary=[];known=None;layout=None
                while cursor<len(lines):
                    line=lines[cursor];cursor+=1
                    if not line.startswith('FAM_STAGE '):ordinary.append('finish' if '$finish called at 9000 (1ps)' in line else line);continue
                    if mode!='observe':raise ValueError('Observer active in disabled control')
                    a=line.split()
                    if len(a)!=3 or int(a[1])!=stage or stage>7:raise ValueError('Missing/reordered native family stage')
                    want_refused=not(stage==0 and timing=='late' or stage==7 or family=='owner' and stage==6)
                    if int(a[2])!=(-1 if want_refused else 0):raise ValueError('Wrong native family admission')
                    if want_refused:
                        if cursor>=len(lines) or lines[cursor]!='FAM_REFUSED_EMPTY':raise ValueError('Missing/partial native refusal')
                        cursor+=1;refused+=1
                    else:
                        start=cursor
                        while cursor<len(lines) and not lines[cursor].startswith('VCL_END '):cursor+=1
                        if cursor==len(lines):raise ValueError('Truncated admitted state')
                        cursor+=1;state=parse(lines[start:cursor]);admitted+=1
                        if state['tick']!=(1000,2000,3000,4000,5000,6000,7000,8000)[stage]:raise ValueError('Wrong native family tick')
                        callbacks=[c for o in state['owners'] for c in o['callbacks']]
                        if len(callbacks)!=1 or not callbacks[0]['function']:raise ValueError('Known sentinel lost or extra callback admitted')
                        if known is None:known=callbacks[0]
                        if callbacks[0]!=known:raise ValueError('Sentinel callback identity changed')
                        owners=[(o['id'],o['pointer'],o['kind'],o['head'],o['wordHead'],o['words']) for o in state['owners']]
                        if layout is None:layout=owners
                        if owners!=layout:raise ValueError('Known owner allocation changed')
                    stage+=1
                expected=[]
                for tick,value in ((3000,1),(4000,3),(5000,11),(6000,7),(8000,5)):
                    if tick!=8000:
                        if family in ('part','array-part') and tick in (4000,6000):expected.append(f'VALUE {tick} F {value} 0 -1')
                        if family=='word':expected.append(f'VALUE {tick} F {value} 0 -1')
                        if family=='array':
                            expected.append(f'VALUE {tick} F {value} 0 0')
                            if tick in (4000,6000):expected.append(f'VALUE {tick} F {2 if tick==4000 else 4} 0 1')
                    expected.append(f'VALUE {tick} K {(tick//1000)-2 if tick<8000 else 5} 0 -1')
                    if family=='owner' and tick!=8000:expected.append(f'PRIVATE_VALUE {0 if tick in (3000,5000) else 1}')
                expected.append('finish')
                if ordinary!=expected:raise ValueError('Changed native callback history/output: '+name+' '+repr(ordinary))
                if stage!=(8 if mode=='observe' else 0):raise ValueError('Missing native lifecycle observations')
                if reference is None:reference=ordinary
                if reference!=ordinary:raise ValueError('Observer changed original continuation')
    return dict(qualified=False,controlsPassed=True,refusals=refused,admissions=admitted,originalContinuationExactlyEqual=True,scope='Native VPI part-select, array-word, whole-array and array-part callbacks plus a native wire-filter subclass, introduced before or after admitted observation. Stateful callbacks refuse caller handoff and complete-list inventory until deferred deletion. Unknown owners refuse even with empty lists, then disappear on destruction. A known callback survives all transitions. Independent output expectations exercise part-select comparison history with full-parent callback values, whole-array indices and subclass behavior.',notEstablished=['Native array-word association-list contents and alias bindings','Registration during active callbacks and reentrant dispatch','Typed referents, compact encoding, operational integration and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/callback_list_families.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    commands += [['iverilog','-g2012','-DFAMILY_OBJECT='+obj,'-o',str(out/(family+'.vvp')),str(out/'probe.v')] for family,obj in FAMILIES.items()]
    for command in commands:subprocess.run(command,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*out.glob('*.vvp'),*modules.glob('*.vpi')];pins={str(p):sha(p) for p in paths};runs={}
    for family in FAMILIES:
        for timing in ('early','late'):
            for mode in ('original','disabled','observe'):
                name=f'{family}-{timing}-{mode}';lib=baseline if mode=='original' else candidate/'vvp/libvvp.so'
                env=dict(os.environ,K7658_FAMILY=family,K7658_TIMING=timing,K7658_MODE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
                cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe',family+'.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
                (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);runs[name]=dict(command=cmd,exitCode=r.returncode,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Changed runtime during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('callback_list_families.py','callback_list_probe.py','net_probe.py','net_types_probe.py','fixtures/callback_list_families.cc','fixtures/callback_list_families.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Native callback family admission controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
