#!/usr/bin/env python3
"""Match live callback code identities without reading unknown optional fields."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def symbols(text):
    result={}
    for line in text.splitlines():
        a=line.split()
        if len(a)!=3 or a[1] not in ('t','T'):continue
        name=a[2][1:] if a[2].startswith('_') else a[2]
        if name not in ('callback','strobe_cb','monitor_cb_2'):continue
        if name in result:raise ValueError('Ambiguous function symbol')
        result[name]=int(a[0],16)
    return result


def snapshot(lines):
    h=lines[0].split()
    if len(h)!=5 or h[:2]!=['VF_BEGIN','1'] or lines[-1]!='VF_END':raise ValueError('Invalid family snapshot')
    now,mode,count=map(int,h[2:]);items=[]
    if now<0 or mode not in range(6) or count<0:raise ValueError('Invalid header')
    for line in lines[1:-1]:
        a=line.split()
        if a[0]=='VF_CB':
            if len(a)!=18 or (items and 'code' not in items[-1]):raise ValueError('Missing code identity')
            v=list(map(int,a[1:-1]));real=float.fromhex(a[-1])
            ident,executing,sync,reason,active,unchanged,known,user,obj,value,nxt,back,timeptr,typ,high,low=v
            if ident<1 or (items and ident<=items[-1]['values'][0]):raise ValueError('Invalid lifetime order')
            if any(x not in (0,1) for x in (executing,sync,active,unchanged,known,nxt,back,timeptr)):
                raise ValueError('Invalid callback flags')
            if not all((unchanged,nxt,back,timeptr)):raise ValueError('Changed callback structure/function')
            if known and (user,obj,value)!=(1,1,1):raise ValueError('Changed known callback referents')
            if not known and (user,obj,value)!=(-1,-1,-1):raise ValueError('Unknown optional fields were interpreted')
            if typ!=2 or high!=0 or not 0<=low<2**32 or real!=0:raise ValueError('Unexpected fixture time')
            if executing and (not active or mode not in (4,5)):raise ValueError('Invalid executing callback')
            items.append({'values':v,'timeReal':real})
        elif a[0]=='VF_CODE':
            if len(a)!=4 or not items or 'code' in items[-1] or int(a[1])!=items[-1]['values'][0]:raise ValueError('Invalid code record')
            if a[2]=='-' or a[3]=='-':raise ValueError('Unresolved fixture function')
            name=bytes.fromhex(a[2]).decode();offset=int(a[3],16)
            if not name or offset<0:raise ValueError('Invalid module address')
            items[-1]['code']={'module':name,'offset':offset}
        else:raise ValueError('Unknown record')
    if len(items)!=count or any('code' not in x for x in items) or sum(x['values'][1] for x in items)>1:
        raise ValueError('Incomplete live callback registry')
    return {'time':now,'mode':mode,'callbacks':items}


def review(root):
    evidence=json.loads((root/'symbols.json').read_text())
    for name,e in evidence.items():
        if symbols((root/(name+'.nm')).read_text())!=e['symbols']:raise ValueError('Changed symbol evidence')
    if sha(root/'probe.vpi')!=evidence['probe.vpi']['sha256']:raise ValueError('Changed fixture module')
    output=None;faults=unknown=executing=canceled=0
    for name in ('baseline','disabled','enabled','corrupt'):
        text=(root/(name+'.stdout')).read_text()
        if (root/(name+'.stderr')).read_text():raise ValueError('Runtime diagnostic')
        actual=[l for l in text.splitlines() if not l.startswith('VF_')]
        if output is None:output=actual
        if output!=actual:raise ValueError('Changed HDL/callback output')
        if [l for l in actual if l.startswith('STROBE ')]!=['STROBE 2000','STROBE 12000','STROBE 22000']:raise ValueError('Missing display callback')
        expected=[f'CALLBACK 0 {base+delay} {idx}' for base in (2000,12000,22000) for delay,idx in ((1000,1),(3000,3))]
        if [l for l in actual if l.startswith('CALLBACK ')]!=expected:raise ValueError('Missing callback/cancellation')
        groups=[];current=[]
        for line in text.splitlines():
            if line.startswith('VF_API '):
                if line!=f'VF_API {int(name!="baseline")}' or current:raise ValueError('Wrong loaded runtime')
                groups.append({'shots':[],'fault':None})
            elif line.startswith('VF_BEGIN '):
                if current or not groups:raise ValueError('Nested/orphan snapshot')
                current=[line]
            elif line=='VF_END':
                if not current:raise ValueError('Orphan end')
                current.append(line);snapshot(current);groups[-1]['shots'].append(current);current=[]
            elif line.startswith(('VF_CB ','VF_CODE ')):
                if not current:raise ValueError('Orphan payload')
                current.append(line)
            elif line.startswith('VF_FAULT '):
                if current or groups[-1]['fault'] is not None:raise ValueError('Invalid fault marker')
                groups[-1]['fault']=int(line.split()[1])
            elif line.startswith('VF_'):raise ValueError('Unknown observer line')
        if current or len(groups)!=9:raise ValueError('Missing observations')
        for i,g in enumerate(groups):
            shots=g['shots'];fault=g['fault'];enabled=name in ('enabled','corrupt')
            expected_fault=int(i%3!=2) if name=='corrupt' else None
            if fault!=expected_fault or len(shots)!=(2+2*(fault==1) if enabled else 0):raise ValueError('Missing fault/observation coverage')
            if not enabled:continue
            if shots[0]!=shots[1]:raise ValueError('Observer changed state')
            state=snapshot(shots[0]);items=state['callbacks'];base=i//3*4
            ids=[base+j for j in ((1,2,3,4),(2,3,4),(4,))[i%3]]
            if [x['values'][0] for x in items]!=ids:raise ValueError('Wrong callback lifetimes')
            if state['mode']!=(3 if i%3==0 else 4) or state['time']!=(2000,12000,22000)[i//3]+(0,1000,3000)[i%3]:raise ValueError('Wrong observation time/mode')
            for item in items:
                v=item['values'];relative=v[0]-base;display=relative==1;known=not display
                is_executing=int(i%3!=0 and relative==(2 if i%3==1 else 4))
                if v[1]!=is_executing or v[2]!=int(display) or v[3]!=(7 if display else 9) or v[4]!=int(relative!=3) or v[6]!=int(known):raise ValueError('Wrong callback family/state')
                module=Path(item['code']['module']).name;symbol='strobe_cb' if display else 'callback'
                if module!=('system.vpi' if display else 'probe.vpi') or item['code']['offset']!=evidence[module]['symbols'][symbol]:raise ValueError('Unidentified loaded function')
                expected_time=0 if display else state['time'] if is_executing else (relative-1)*1000
                if v[15]!=expected_time:raise ValueError('Changed callback time')
                unknown+=int(display);executing+=is_executing;canceled+=int(not v[4])
            if fault:
                altered=snapshot(shots[2]);restored=snapshot(shots[3])
                if restored!=state or altered==state or altered['time']!=state['time'] or altered['mode']!=state['mode'] or len(altered['callbacks'])!=len(items):raise ValueError('Unrestored/unrelated fault')
                changes=[(a,b) for a,b in zip(items,altered['callbacks']) if a!=b]
                if len(changes)!=1:raise ValueError('Wrong mutation count')
                a,b=changes[0];av=a['values'];bv=b['values']
                if av[1] or not av[4] or av[:2]+av[3:]!=bv[:2]+bv[3:] or av[2]==bv[2] or a['code']!=b['code']:raise ValueError('Wrong mutation target')
                faults+=1
    if (faults,unknown,executing,canceled)!=(6,6,12,12):raise ValueError('Incomplete family coverage')
    return {'completed':True,'qualified':False,'timestampedOutputExactlyEqual':True,'modeMutationsDetectedAndRestored':faults,
            'legacyUnsafeApiRejected':True,'displayFunctionIdentifiedByModuleOffset':True,'unknownOptionalFieldsNotInterpreted':True,'displayObservations':unknown,
            'executingObservations':executing,'canceledObservations':canceled,
            'scope':'Standalone pinned-module callback identification and safe partial header observation, including actual $strobe.',
            'notEstablished':['Display user-data contents and lifetimes','Optional fields of arbitrary callback families','Board integration and general rollback','Executing wrapper/stack and freed storage']}


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed candidate build')
    for ext in ('c','v'):shutil.copyfile(HERE/f'fixtures/private_sync_family_probe.{ext}',out/f'probe.{ext}')
    subprocess.run(['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],check=True)
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    subprocess.run(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')],check=True)
    identities={}
    for module in (out/'probe.vpi',modules/'system.vpi'):
        text=subprocess.check_output(['nm','-an',str(module)],text=True);(out/(module.name+'.nm')).write_text(text)
        identities[module.name]={'path':str(module),'sha256':sha(module),'symbols':symbols(text)}
    (out/'symbols.json').write_text(json.dumps(identities,indent=2)+'\n')
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    runtime={str(p):sha(p) for p in paths};commands={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_FAMILY_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];commands[name]=cmd
        p=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(p.stdout);(out/(name+'.stderr')).write_text(p.stderr);p.check_returncode()
    if any(sha(Path(p))!=h for p,h in runtime.items()):raise ValueError('Changed runtime')
    result=review(out);result.update(runtime=runtime,commands=commands,candidateBuildSha256=sha(candidate/'build.json'),
        sources={n:sha(HERE/n) for n in ('private_sync_family_probe.py','fixtures/private_sync_family_probe.c','fixtures/private_sync_family_probe.v','build_private_sync_family.py','engine-patches/icarus-sync-family-observer.patch','engine-patches/icarus-sync-observer.patch','engine-patches/icarus-queue-observer.patch')})
    shutil.copyfile(candidate/'build.json',out/'build.json');(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'assessment.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        result=review(a.check);retained=json.loads((a.check/'assessment.json').read_text())
        if any(retained.get(k)!=v for k,v in result.items()):raise ValueError('Changed assessment')
        for e in json.loads((a.check/'symbols.json').read_text()).values():
            if retained['runtime'].get(e['path'])!=e['sha256']:raise ValueError('Changed module identity')
        print('Callback-family controls verified; payload and board qualification remain open.')
    else:
        if any(x is None for x in (a.candidate,a.baseline,a.modules,a.out)):p.error('Need candidate, baseline, modules and out')
        run(a.candidate,a.baseline,a.modules,a.out)
