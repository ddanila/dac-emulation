#!/usr/bin/env python3
"""Verify native exact-owner birth, destruction and same-address reincarnation."""
import argparse,copy,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from callback_delta import separate
from callback_list_probe import parse
from net_probe import pointer
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text());totals=dict(images=0,denseBytes=0,deltaBytes=0,referenceBytes=0,refusals=0);lifetimes=0
    for timing in ('early','late'):
        expected=[]
        for stage in range(7):
            if stage in (3,5,6):expected.append('OWN_DROP '+{3:'0 1',5:'1 1',6:'0 2'}[stage])
            expected.append('S'+str(stage))
            if stage==0 and timing=='early':expected.append('OWN_VALUE 0 1 1 0')
            if stage in (1,2):expected.append('OWN_VALUE 0 1 1 1')
            if stage in (4,5):expected.append('OWN_VALUE 0 2 80 '+'z'*80)
            if stage in (2,3,4):expected.append('OWN_VALUE 1 1 9 '+'x'*9)
        expected+=['KEEP 0','finish']
        for mode in ('baseline','disabled','enabled'):
            name=f'{timing}-{mode}'
            if receipt['runs'][name]['exitCode'] or (root/(name+'.stderr')).read_text():raise ValueError('Failed native owner lifecycle')
            lines,stats=separate((root/(name+'.stdout')).read_text().splitlines())
            for k,v in stats.items():totals[k]+=v
            cursor=stage=0;events=[];bindings={};active={};known_ids={};anchor=None;retired=set();old_ids=set()
            def consume(wanted):
                nonlocal cursor
                if cursor>=len(lines) or lines[cursor]!=wanted:raise ValueError('Expected '+wanted)
                cursor+=1
            def snapshot():
                nonlocal cursor
                start=cursor
                while cursor<len(lines) and not lines[cursor].startswith('VCL_END '):cursor+=1
                if cursor==len(lines):raise ValueError('Truncated owner lifecycle')
                cursor+=1;return parse(lines[start:cursor])
            while cursor<len(lines):
                line=lines[cursor]
                if line.startswith('OWN_BIND '):
                    a=line.split();cursor+=1
                    if mode!='enabled' or len(a)!=4:raise ValueError('Invalid native owner binding')
                    slot,generation=int(a[1]),int(a[2]);key=(slot,generation);address=pointer(a[3])
                    if slot not in (0,1) or key in bindings or slot in active or not address:raise ValueError('Aliased native owner generation')
                    if generation==2 and (slot!=0 or bindings.get((0,1))!=address):raise ValueError('Missing same-address reincarnation')
                    bindings[key]=address;active[slot]=generation;continue
                if line.startswith('OWN_DROP '):
                    a=line.split();slot,generation=map(int,a[1:]);events.append(line);cursor+=1
                    if mode=='enabled':
                        if active.pop(slot,None)!=generation:raise ValueError('Wrong owner retirement')
                        retired.add(known_ids[slot,generation])
                    continue
                if not line.startswith('OWN_STAGE '):events.append('finish' if '$finish called at 8000 (1ps)' in line else line);cursor+=1;continue
                consume(f'OWN_STAGE {stage}');events.append('S'+str(stage))
                if mode=='enabled':
                    consume('OWN_BEFORE');state=snapshot();consume('OWN_REPEAT')
                    if snapshot()!=state or state['tick']!=(stage+1)*1000:raise ValueError('Changed native owner observation')
                    owners=state['owners'];by_address={o['pointer']:o for o in owners}
                    for slot,generation in active.items():
                        key=(slot,generation);owner=by_address.get(bindings[key])
                        if owner is None or owner['callbacks'] or owner['words'] or owner['id'] in retired:raise ValueError('Missing/retired native owner')
                        if key not in known_ids:
                            if owner['id'] in old_ids or old_ids and owner['id']<=max(old_ids):raise ValueError('Reused owner lifetime')
                            known_ids[key]=owner['id'];old_ids.add(owner['id']);lifetimes+=1
                        if known_ids[key]!=owner['id']:raise ValueError('Changed native owner lifetime')
                    actual=[o for o in owners if o['pointer'] not in {bindings[k,g] for k,g in active.items()}]
                    if anchor is None:anchor=actual
                    if actual!=anchor or any(o['id'] in retired for o in owners):raise ValueError('Lost anchor or resurrected retired owner')
                # Values are between the image and DONE; consume them explicitly.
                while cursor<len(lines) and lines[cursor].startswith('OWN_VALUE '):events.append(lines[cursor]);cursor+=1
                if cursor<len(lines) and lines[cursor]==f'OWN_DONE {stage}':cursor+=1
                else:raise ValueError('Missing owner stage completion')
                stage+=1
            if stage!=7 or events!=expected:raise ValueError('Changed native lifecycle continuation: '+repr(events))
            if mode=='enabled' and (set(bindings)!={(0,1),(1,1),(0,2)} or active):raise ValueError('Incomplete owner lifecycle coverage')
    return dict(qualified=False,controlsPassed=True,compact=totals,nativeOwnerLifetimes=lifetimes,originalContinuationExactlyEqual=True,scope='Exact native vvp_wire_vec4 owners constructed before or after compact reference, destroyed, and reconstructed at the same storage address with fresh lifetime IDs. Complete dense/compact images preserve persistent owners, additions and explicit reference-owner removal. Native constructor values and a filter write agree with original execution. Test-owned storage uses placement construction/destruction; no board allocation behavior is inferred.',notEstablished=['Array-word association allocation/removal on live owners','Deep typed referents and combined operational integration','Suspended traversal and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed compact runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/callback_owner_lifecycle.{ext}',out/f'probe.{ext}')
    shutil.copy2(HERE/'fixtures/callback_delta_adapter.h',out/'compact.h')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for timing in ('early','late'):
        for mode in ('baseline','disabled','enabled'):
            name=f'{timing}-{mode}';lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,K7658_OWNER_MODE='on' if mode=='enabled' else 'off',K7658_OWNER_TIMING=timing);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
            (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);runs[name]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Changed runtime during owner lifecycle')
    shutil.copy2(candidate/'build.json',out/'build.json');(out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('callback_owner_lifecycle.py','callback_delta.py','callback_list_probe.py','fixtures/callback_owner_lifecycle.cc','fixtures/callback_owner_lifecycle.v','fixtures/callback_delta_adapter.h')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed owner lifecycle assessment')
        print('Native compact owner lifecycle verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
