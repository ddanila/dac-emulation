#!/usr/bin/env python3
"""Validate queued primitive payloads and restored faults on the real runtime."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def parse_snapshot(lines):
    if len(lines)<2 or lines[0].split()[:2]!=['VPR_BEGIN','1'] or len(lines[0].split())!=3:
        raise ValueError('Invalid primitive header')
    tick=int(lines[0].split()[2]);events=[];wrappers=set();objects=set();positions=set();i=1
    while i<len(lines)-1:
        a=lines[i].split()
        if len(a)!=8 or a[0]!='VPR_EVENT' or i+1>=len(lines)-1:raise ValueError('Incomplete primitive wrapper')
        slot,ordinal,wrapper,identity,kind,delete=map(int,(a[1],a[3],a[4],a[5],a[6],a[7]))
        if slot< -1 or ordinal<0 or min(wrapper,identity)<1 or kind not in (1,2) or delete not in (0,1):raise ValueError('Invalid primitive identity')
        if a[2] not in ('init','final','start','active','inactive','nbassign','rwsync','rosync','del_thr'):raise ValueError('Invalid queue region')
        if wrapper in wrappers or identity in objects or (slot,a[2],ordinal) in positions:raise ValueError('Aliased queued primitive')
        wrappers.add(wrapper);objects.add(identity);positions.add((slot,a[2],ordinal))
        d=lines[i+1].split();i+=2
        if len(d)!=7 or d[0]!='VPR_DATA' or int(d[1])!=kind:raise ValueError('Mismatched primitive payload')
        target=0 if d[2]=='(nil)' else int(d[2],16)
        base,width,size=map(int,d[3:6]);bits=d[6]
        if min(base,width,size,target)<0 or (not size and bits!='-') or (size and (len(bits)!=size or any(c not in '0123' for c in bits))):raise ValueError('Invalid initialized vector contents')
        if kind==1 and (base or width):raise ValueError('Inverter has no slice bounds')
        if kind==2 and width!=size:raise ValueError('Part-select vector/width mismatch')
        events.append(dict(slot=slot,region=a[2],ordinal=ordinal,wrapper=wrapper,id=identity,kind=kind,delete=delete,target=target,base=base,width=width,size=size,bits=bits))
    footer=lines[-1].split()
    if len(footer)!=3 or footer[0]!='VPR_END' or int(footer[1])!=len(events) or int(footer[2])<0 or tick<0:raise ValueError('Invalid primitive footer')
    return {'tick':tick,'events':events,'unsupportedEvents':int(footer[2])}


def review(root):
    expected=['CHANGE 0 0123456789abcdef0123 fedcba9876543210fedc 12',
              'CHANGE 1000 fedcba9876543210fedc 0123456789abcdef0123 ed',
              'CHANGE 3000 0123456789abcdef0123 fedcba9876543210fedc 12']
    output=None;normalized=None;faults=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if (root/(mode+'.stderr')).read_text():raise ValueError('Simulator diagnostic')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('VPM_','VPR_'))]
        if output is None:output=ordinary
        if ordinary!=output or [l for l in ordinary if l.startswith('CHANGE ')]!=expected:raise ValueError('Changed output timing or value')
        control=[l for l in lines if l.startswith(('VPM_','VPR_'))];cursor=0;stages=[]
        def consume(wanted):
            nonlocal cursor
            if cursor>=len(control) or control[cursor]!=wanted:raise ValueError('Missing/reordered control: '+wanted)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(control) and not control[cursor].startswith('VPR_END '):cursor+=1
            if cursor==len(control):raise ValueError('Incomplete primitive snapshot')
            cursor+=1;return parse_snapshot(control[start:cursor])
        for stage in range(4):
            consume(f'VPM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VPM_BEFORE');before=snapshot();consume('VPM_REPEAT')
                if snapshot()!=before:raise ValueError('Unstable observation')
                if any(not e['target'] or e['delete'] for e in before['events']):raise ValueError('Missing pending destination or incorrect ownership')
                stages.append(before)
                if mode=='corrupt':
                    for kind in (1,2):
                        targets=[i for i,e in enumerate(before['events']) if e['kind']==kind]
                        if not targets:continue
                        for field in range(2 if kind==1 else 3):
                            consume(f'VPM_CHANGED {kind} {field}');changed=snapshot();consume('VPM_RESTORED')
                            if snapshot()!=before:raise ValueError('Unrestored primitive')
                            consume(f'VPM_FAULT {kind} {field} 1 1')
                            if changed['tick']!=before['tick'] or changed['unsupportedEvents']!=before['unsupportedEvents'] or len(changed['events'])!=len(before['events']):raise ValueError('Changed queue scope')
                            key=('bits','target','base')[field];index=targets[0]
                            for i,(a,b) in enumerate(zip(before['events'],changed['events'])):
                                if {k for k in a if a[k]!=b[k]}!=({key} if i==index else set()):raise ValueError('Wrong primitive payload fault')
                            if key=='target' and changed['events'][index]['target']!=0:raise ValueError('Wrong destination fault')
                            if key=='base' and changed['events'][index]['base']!=(before['events'][index]['base']^1):raise ValueError('Wrong slice fault')
                            faults+=1
            consume(f'VPM_DONE {stage}')
        if cursor!=len(control):raise ValueError('Unexpected observer record')
        if stages:
            if [s['tick'] for s in stages]!=[1000,2000,3000,4000] or stages[1]['events'] or stages[3]['events']:raise ValueError('Missing primitive consumption')
            bits=lambda n,width:format(n,'0'+str(width)+'b')[::-1]
            for index,value in ((0,0xfedcba9876543210fedc),(2,0x0123456789abcdef0123)):
                events=stages[index]['events']
                if [e['kind'] for e in events]!=[1,2] or [(e['base'],e['width'],e['size'],e['bits']) for e in events]!=[(0,0,80,bits(value,80)),(4,8,8,bits((value>>4)&255,8))]:raise ValueError('Wrong cached inverter/part-select payload')
            old,new=stages[0]['events'],stages[2]['events']
            if [e['id'] for e in old]!=[e['id'] for e in new] or min(e['wrapper'] for e in new)<=max(e['wrapper'] for e in old):raise ValueError('Primitive/wrapper lifetime relationship changed')
            targets={};canonical=[]
            for s in stages:
                events=[]
                for e in s['events']:
                    if e['target'] not in targets:targets[e['target']]=len(targets)+1
                    events.append(dict(e,target=targets[e['target']]))
                canonical.append(dict(s,events=events))
            if normalized is None:normalized=canonical
            elif canonical!=normalized:raise ValueError('Fault controls changed normal primitive trajectory')
    return {'completed':True,'qualified':False,'simulationOutputExactlyEqual':True,'restoredFaults':faults,
            'scope':'Queued inverter and static part-select initialized cached vectors, pending destination pointers, slice bounds, stable primitive lifetimes and fresh wrapper lifetimes on requeue. Complete timestamped fixture transitions match original/disabled/observed/restored controls.',
            'notEstablished':['Board integration','Transmission-gate island and thread state','Destination net contents','Freed-storage equivalence and general rollback']}


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/primitive_probe.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_PRIMITIVE_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('primitive_probe.py','fixtures/primitive_probe.c','fixtures/primitive_probe.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Primitive payload controls verified; board and general rollback coverage remain open.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need all runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
