#!/usr/bin/env python3
"""Validate pending assignment payloads and restored faults on the real runtime."""
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
    if len(lines)<2 or lines[0].split()[:2]!=['VAP_BEGIN','1'] or len(lines[0].split())!=3:
        raise ValueError('Invalid assignment header')
    tick=int(lines[0].split()[2]);events=[];keys=set();ids=set();counts=[0,0]
    for line in lines[1:-1]:
        a=line.split()
        if len(a)!=12 or a[0]!='VAP_EVENT':raise ValueError('Invalid assignment record')
        slot,ordinal,identity,kind,port,base,width,size=map(int,(a[1],a[3],a[4],a[5],a[7],a[8],a[9],a[10]))
        if slot< -1 or ordinal<0 or identity<1 or kind not in (4,8) or port not in range(4) or min(base,width,size)<0:
            raise ValueError('Invalid assignment metadata')
        if a[2] not in ('init','final','start','active','inactive','nbassign','rwsync','rosync','del_thr') or not a[6].startswith('0x') or int(a[6],16)==0:
            raise ValueError('Unknown queue or missing destination')
        if (slot,a[2],ordinal) in keys or identity in ids:raise ValueError('Aliased event identity/position')
        keys.add((slot,a[2],ordinal));ids.add(identity);counts[kind==8]+=1
        bits=a[11]
        if (not size and bits!='-') or (size and len(bits)!=size*(1 if kind==4 else 3)):
            raise ValueError('Incomplete vector')
        if size:
            if kind==4 and any(c not in '0123' for c in bits):raise ValueError('Invalid four-state value')
            if kind==8 and any(c not in ('0123' if i%3==0 else '01234567') for i,c in enumerate(bits)):raise ValueError('Invalid strength encoding')
        if kind==8 and (base or width):raise ValueError('Unexpected strength slice fields')
        events.append(dict(slot=slot,region=a[2],ordinal=ordinal,id=identity,kind=kind,target=a[6],port=port,base=base,width=width,size=size,bits=bits))
    end=lines[-1].split()
    if len(end)!=4 or end[0]!='VAP_END' or list(map(int,end[1:3]))!=counts or int(end[3])<0 or tick<0:
        raise ValueError('Missing/count-mismatched assignment footer')
    return {'tick':tick,'events':events,'unsupportedEvents':int(end[3])}


def review(root):
    expected=['VALUES 1000 00 0123456789abcdef0123 fedcba9876543210fedc 10xz',
              'VALUES 16000 c5 fedcba9876543210fedc 0123456789abcdef0123 10xz']
    expected_changes=['CHANGE 0 00 0123456789abcdef0123 10xz',
                      'CHANGE 8000 00 fedcba9876543210fedc 10xz',
                      'CHANGE 10000 a5 fedcba9876543210fedc 10xz',
                      'CHANGE 12000 c5 fedcba9876543210fedc 10xz']
    output=None;normalized=None;faults=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if (root/(mode+'.stderr')).read_text():raise ValueError('Simulator diagnostic')
        lines=(root/(mode+'.stdout')).read_text().splitlines()
        ordinary=[l for l in lines if not l.startswith(('VAM_','VAP_'))]
        if output is None:output=ordinary
        if ordinary!=output or [l for l in ordinary if l.startswith('VALUES ')]!=expected:
            raise ValueError('Changed simulation continuation')
        if [l for l in ordinary if l.startswith('CHANGE ')]!=expected_changes:raise ValueError('Changed assignment timing or value')
        control=[l for l in lines if l.startswith(('VAM_','VAP_'))];cursor=0;stages=[]
        def consume(wanted):
            nonlocal cursor
            if cursor>=len(control) or control[cursor]!=wanted:raise ValueError('Missing/reordered control: '+wanted)
            cursor+=1
        def snapshot():
            nonlocal cursor
            start=cursor
            while cursor<len(control) and not control[cursor].startswith('VAP_END '):cursor+=1
            if cursor==len(control):raise ValueError('Incomplete snapshot')
            cursor+=1;return parse_snapshot(control[start:cursor])
        for stage in range(3):
            consume(f'VAM_API {stage} {int(mode!="baseline")}')
            if mode in ('enabled','corrupt'):
                consume('VAM_BEFORE');before=snapshot();consume('VAM_REPEAT')
                if snapshot()!=before:raise ValueError('Unstable observation')
                stages.append(before)
                if mode=='corrupt':
                    for kind in (4,8):
                        targets=[i for i,e in enumerate(before['events']) if e['kind']==kind and e['size']]
                        if not targets:continue
                        for field in range(3):
                            consume(f'VAM_CHANGED {kind} {field}');changed=snapshot();consume('VAM_RESTORED')
                            if snapshot()!=before:raise ValueError('Unrestored payload')
                            consume(f'VAM_FAULT {kind} {field} 1 1')
                            if changed['tick']!=before['tick'] or changed['unsupportedEvents']!=before['unsupportedEvents'] or len(changed['events'])!=len(before['events']):raise ValueError('Changed queue scope')
                            index=targets[0];key='port' if field==1 else 'width' if field==2 and kind==4 else 'bits'
                            for i,(a,b) in enumerate(zip(before['events'],changed['events'])):
                                difference={k for k in a if a[k]!=b[k]}
                                if difference!=({key} if i==index else set()):raise ValueError('Wrong payload fault')
                            if key in ('port','width') and changed['events'][index][key]!=(before['events'][index][key]^1):raise ValueError('Wrong target/slice fault')
                            faults+=1
            consume(f'VAM_DONE {stage}')
        if cursor!=len(control):raise ValueError('Unexpected observer records')
        if stages:
            if [s['tick'] for s in stages]!=[0,1000,16000] or stages[2]['events']:raise ValueError('Wrong lifetime window')
            first=stages[0]['events'];later=stages[1]['events']
            if [e['kind'] for e in first]!=[4,4,4,8,4,4,4] or [e['size'] for e in first]!=[80,80,80,4,1,1,1]:raise ValueError('Missing startup payload families')
            if first[3]['bits']!='200336033166':raise ValueError('Missing strength/X/Z payload')
            bits=lambda value,width:format(value,'0'+str(width)+'b')[::-1]
            required=[(80,0,0,bits(0xfedcba9876543210fedc,80)),(8,0,0,bits(0xa5,8)),(4,4,8,bits(0xc,4))]
            if [(e['size'],e['base'],e['width'],e['bits']) for e in later]!=required or any(e['kind']!=4 or e['region']!='nbassign' for e in later):raise ValueError('Missing delayed/partial assignment contents')
            if min(e['id'] for e in later)<=max(e['id'] for e in first):raise ValueError('Reused assignment lifetime')
            targets={};canonical=[]
            for s in stages:
                events=[]
                for e in s['events']:
                    if e['target'] not in targets:targets[e['target']]=len(targets)+1
                    events.append(dict(e,target=targets[e['target']]))
                canonical.append(dict(s,events=events))
            if normalized is None:normalized=canonical
            elif canonical!=normalized:raise ValueError('Fault controls altered normal payload trajectory')
    return {'completed':True,'qualified':False,'simulationOutputExactlyEqual':True,'restoredFaults':faults,
            'scope':'Queued vector4/vector8 values, X/Z and strengths, opaque destination/port, partial-assignment bounds, wide-vector storage and constructor/destructor lifetime identities. Original/disabled/observed/restored controls preserve full fixture output.',
            'notEstablished':['Board integration','Destination contents and topology validity','Thread, primitive and other event payloads','Freed-storage equivalence and general rollback']}


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/f'fixtures/assignment_probe.{ext}',out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_ASSIGNMENT_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('assignment_probe.py','fixtures/assignment_probe.c','fixtures/assignment_probe.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Assignment payload controls verified; board and general rollback coverage remain open.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need all runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
