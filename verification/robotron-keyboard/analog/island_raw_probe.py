#!/usr/bin/env python3
"""Qualify raw island caches at idle and synchronous output callback boundaries."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from net_probe import pointer
from wire_raw_probe import triplet
from island_probe import parse_snapshot,validate_normal
HERE=Path(__file__).resolve().parent
FIELDS=('in','out','scratch')

def parse(lines):
    h=lines[0].split()
    if len(h)!=3 or h[:2]!=['VIR_BEGIN','1']:raise ValueError('Invalid raw island header')
    islands=[];i=1
    while i<len(lines)-1:
        a=lines[i].split();i+=1
        if len(a)!=4 or a[0]!='VIR_ISLAND':raise ValueError('Missing raw island')
        n=dict(id=int(a[1]),key=pointer(a[2]),ports=[]);count=int(a[3])
        if n['id']<=0 or not n['key'] or count<0 or islands and n['id']<=islands[-1]['id']:raise ValueError('Invalid island identity/order')
        for index in range(1,count+1):
            a=lines[i].split();i+=1
            if len(a)!=5 or a[:2]!=['VIR_PORT',str(index)]:raise ValueError('Invalid raw port')
            p=dict(id=index,net=pointer(a[2]),functor=pointer(a[3]),filter=pointer(a[4]),vectors={})
            if not p['net'] or not p['functor']:raise ValueError('Missing port binding')
            for field in range(3):
                a=lines[i].split();i+=1
                if len(a)!=4 or a[:2]!=['VIR_VECTOR',str(field)]:raise ValueError('Missing raw vector')
                value=b'' if a[3]=='-' else bytes.fromhex(a[3])
                if len(value)!=int(a[2]):raise ValueError('Wrong raw width')
                p['vectors'][FIELDS[field]]=value
            n['ports'].append(p)
        if len({p['net'] for p in n['ports']})!=count:raise ValueError('Aliased raw port')
        islands.append(n)
    if int(h[2])<0 or i!=len(lines)-1 or lines[-1]!=f'VIR_END {len(islands)}':raise ValueError('Incomplete raw inventory')
    return dict(tick=int(h[2]),islands=islands)

def bind(raw,legacy):
    expected=copy.deepcopy(legacy)
    for island in expected['islands']:
        island.pop('flag');island.pop('head');island.pop('branches')
        for port in island['ports']:
            port['vectors']={k:v['bits'] for k,v in port['vectors'].items()}
    actual=copy.deepcopy(raw)
    for island in actual['islands']:
        for port in island['ports']:
            port['vectors']={k:''.join(triplet(b) for b in v) if v else '-' for k,v in port['vectors'].items()}
    if actual!=expected:raise ValueError('Raw island differs from legacy bindings/values')

def mutation(before,field,operation):
    result=copy.deepcopy(before)
    for island in result['islands']:
        for port in island['ports']:
            v=bytearray(port['vectors'][FIELDS[field]])
            if operation!=2 and (not v or operation==1 and not any(b in (0,136) for b in v)):continue
            if operation==2:v=bytearray(len(v)+1)
            else:
                index=next(i for i,b in enumerate(v) if b in (0,136)) if operation==1 else 0
                v[index]=v[index]^136 if operation==1 else 102 if v[index]==238 else 238
            port['vectors'][FIELDS[field]]=bytes(v);return result
    return None

def review(root):
    receipt=json.loads((root/'run.json').read_text());ordinary_reference=None;faults={};observations=live_scratch=callbacks=0
    for mode in ('baseline','disabled','enabled','corrupt'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Native control failed')
        lines=(root/(mode+'.stdout')).read_text().splitlines();cursor=stage=idle=0;ordinary=[];bindings=None
        def consume(want):
            nonlocal cursor
            if cursor>=len(lines) or lines[cursor]!=want:raise ValueError('Expected '+want)
            cursor+=1
        def snapshot(raw=True):
            nonlocal cursor
            start=cursor;marker='VIR_END ' if raw else 'VI_END '
            while cursor<len(lines) and not lines[cursor].startswith(marker):cursor+=1
            if cursor==len(lines):raise ValueError('Truncated island state')
            cursor+=1;return parse(lines[start:cursor]) if raw else parse_snapshot(lines[start:cursor])
        while cursor<len(lines):
            line=lines[cursor]
            if not line.startswith('IRM_STAGE '):ordinary.append(line);cursor+=1;continue
            a=line.split()
            if len(a)!=4 or int(a[1])!=stage or a[2] not in ('0','1') or int(a[3])!=int(mode!='baseline'):raise ValueError('Wrong observation stage')
            callback=int(a[2]);ordinary.append(f'callback {callback}');idle+=not callback;cursor+=1
            if mode in ('enabled','corrupt'):
                consume('IRM_BEFORE');before=snapshot();legacy=snapshot(False);validate_normal(legacy);bind(before,legacy)
                topology=copy.deepcopy(before);topology.pop('tick')
                for island in topology['islands']:
                    for port in island['ports']:port.pop('vectors')
                if bindings is None:bindings=topology
                elif bindings!=topology:raise ValueError('Island allocation rebound')
                consume('IRM_REPEAT')
                if snapshot()!=before:raise ValueError('Observer changed state')
                observations+=1;callbacks+=callback
                live_scratch+=bool(callback and any(p['vectors']['scratch'] for n in before['islands'] for p in n['ports']))
                if mode=='corrupt':
                    for field in range(3):
                        for operation in range(3):
                            expected=mutation(before,field,operation)
                            if expected is None:continue
                            consume(f'IRM_CHANGED {field} {operation}');changed=snapshot();old=snapshot(False);bind(changed,old)
                            if changed!=expected:raise ValueError('Wrong raw fault or unrelated change')
                            if operation==1 and old!=legacy:raise ValueError('Collision visible to legacy encoding')
                            consume('IRM_RESTORED')
                            if snapshot()!=before:raise ValueError('Raw fault not restored')
                            consume(f'IRM_FAULT {field} {operation} 1 1');key=f'{field}:{operation}';faults[key]=faults.get(key,0)+1
            consume(f'IRM_DONE {stage}');stage+=1
        if idle!=7 or not any('$finish called at 8000 (1ps)' in l for l in ordinary):raise ValueError('Incomplete fixture')
        if ordinary_reference is None:ordinary_reference=ordinary
        elif ordinary!=ordinary_reference:raise ValueError('Changed original-runtime continuation')
    if set(faults)!={f'{f}:{op}' for f in range(3) for op in range(3)} or not live_scratch:raise ValueError('Missing raw field/live scratch controls')
    expected=['CHANGE 0 0 1010 zzzz','CHANGE 1000 1 1010 1010','CHANGE 3000 x 1010 xxxx','CHANGE 4000 x xxxx 0101','CHANGE 5000 0 zzzz 0101','CHANGE 6000 1 1100 1100']
    if [l for l in ordinary_reference if l.startswith('CHANGE ')]!=expected:raise ValueError('Changed fixture outputs')
    return dict(qualified=False,controlsPassed=True,observations=observations,callbackObservations=callbacks,liveScratchObservations=live_scratch,faultsByField=faults,originalContinuationExactlyEqual=True,rawAndLegacyBindingsAgree=True,hiddenCollisionFaultsDetected=True,scope='Native tranif fixture input/output/scratch raw bytes observed at idle and synchronous value callbacks before scratch clearing. Restored byte, width and hidden raw HiZ collision faults preserve original continuation and legacy graph/topology bindings.',notEstablished=['Native unsupported-family and allocation-growth controls','Direct partial/raw-strength input coverage, wider vectors and other switch families','Scheduled vector-8 assignment payloads, compact encoding and operational integration','Freed storage and general rollback'])


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/island_raw_probe.c' if ext=='c' else 'fixtures/island_probe.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_ISLAND_RAW_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('island_raw_probe.py','island_probe.py','wire_raw_probe.py','net_probe.py','fixtures/island_raw_probe.c','fixtures/island_probe.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')



if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Idle-island runtime controls verified; board and referent coverage remain open.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
