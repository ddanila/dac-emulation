#!/usr/bin/env python3
"""Validate executing generic-event identity, ownership and restored faults."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from private_sync_family_probe import snapshot as callback_snapshot,symbols
HERE=Path(__file__).resolve().parent


def bundle(lines):
    if lines[0]!='VX_BEGIN' or lines[-1]!='VX_END':raise ValueError('Invalid executing bundle')
    end=lines.index('VF_END');callbacks=callback_snapshot(lines[1:end+1]);wrapper=lines[end+1:-1]
    h=wrapper[0].split()
    if len(h)!=3 or h[:2]!=['VE_BEGIN','1'] or wrapper[-1]!='VE_END':raise ValueError('Invalid wrapper header')
    frames=[]
    for line in wrapper[1:-1]:
        a=line.split()
        if len(a)!=5 or a[0]!='VE_FRAME':raise ValueError('Invalid wrapper frame')
        ordinal,ident,callback,delete=map(int,a[1:])
        if ordinal!=len(frames) or ident<1 or callback<1 or delete not in (0,1):raise ValueError('Invalid frame state')
        frames.append({'id':ident,'callbackId':callback,'deleteObject':delete})
    executing=[cb['values'][0] for cb in callbacks['callbacks'] if cb['values'][1]]
    if len(frames)!=int(h[2]) or [f['callbackId'] for f in frames]!=executing:raise ValueError('Unlinked executing callback/frame')
    return {'callbacks':callbacks,'frames':frames}


def review(root):
    symbol=json.loads((root/'symbols.json').read_text())
    if symbols((root/'probe.vpi.nm').read_text()).get('callback')!=symbol['offset'] or sha(root/'probe.vpi')!=symbol['sha256']:
        raise ValueError('Changed callback module evidence')
    output=None;faults=executing=empty=0;reasons=set()
    for name in ('baseline','disabled','enabled','corrupt'):
        text=(root/(name+'.stdout')).read_text()
        if (root/(name+'.stderr')).read_text():raise ValueError('Simulator diagnostic')
        actual=[l for l in text.splitlines() if not l.startswith(('VX_','VE_','VF_'))]
        if output is None:output=actual
        if output!=actual:raise ValueError('Changed HDL/callback continuation')
        expected=[f'CALLBACK 0 {t+delay} {reason} {index}' for t in (2000,12000,22000) for delay,reason,index in ((0,6,2),(0,7,3),(1000,9,1))]
        if [l for l in actual if l.startswith('CALLBACK ')]!=expected:raise ValueError('Wrong callback order/reason/time')
        groups=[];current=[]
        for line in text.splitlines():
            if line.startswith('VX_API '):
                if current or line!=f'VX_API {int(name!="baseline")}':raise ValueError('Wrong loaded runtime API')
                groups.append({'shots':[],'fault':None})
            elif line=='VX_BEGIN':
                if current or not groups:raise ValueError('Nested/orphan observation')
                current=[line]
            elif line=='VX_END':
                if not current:raise ValueError('Orphan end')
                current.append(line);bundle(current);groups[-1]['shots'].append(current);current=[]
            elif line.startswith(('VF_','VE_')):
                if not current:raise ValueError('Orphan callback/frame data')
                current.append(line)
            elif line.startswith('VX_FAULT '):
                if current or not groups or groups[-1]['fault'] is not None:raise ValueError('Invalid fault marker')
                groups[-1]['fault']=int(line.split()[1])
            elif line.startswith('VX_'):raise ValueError('Unknown wrapper record')
        if current or len(groups)!=15:raise ValueError('Missing observation boundaries')
        live_ids=set()
        for i,g in enumerate(groups):
            stage=i%5;sequence=i//5;active=stage in (1,2,3);shots=g['shots'];fault=g['fault'];enabled=name in ('enabled','corrupt')
            if fault!=(int(active) if name=='corrupt' else None) or len(shots)!=(2+2*int(name=='corrupt' and active) if enabled else 0):raise ValueError('Missing mutation/observation')
            if not enabled:continue
            if shots[0]!=shots[1]:raise ValueError('Observer changed state')
            state=bundle(shots[0]);callbacks=state['callbacks'];frames=state['frames']
            if callbacks['time']!=(2000,12000,22000)[sequence]+(0,0,0,1000,4000)[stage] or callbacks['mode']!=(3,4,5,4,3)[stage]:raise ValueError('Wrong observation time/mode')
            ids=[sequence*4+n for n in ((1,2,3,4),(1,2,3,4),(1,3,4),(1,4),())[stage]]
            if [cb['values'][0] for cb in callbacks['callbacks']]!=ids:raise ValueError('Changed callback lifecycle')
            for cb in callbacks['callbacks']:
                if cb['code']!={'module':symbol['path'],'offset':symbol['offset']} or cb['values'][6]!=1:raise ValueError('Unknown callback function')
            if active:
                expected_id=sequence*4+(2,3,1)[stage-1]
                if len(frames)!=1 or frames[0]['callbackId']!=expected_id or frames[0]['deleteObject']!=0 or frames[0]['id'] in live_ids:raise ValueError('Wrong executing event identity/ownership')
                live_ids.add(frames[0]['id']);executing+=1;reasons.add((6,7,9)[stage-1])
            else:
                if frames:raise ValueError('Stale executing frame')
                empty+=1
            if name=='corrupt' and active:
                changed=bundle(shots[2]);restored=bundle(shots[3])
                wanted=json.loads(json.dumps(state));wanted['frames'][0]['deleteObject']=1
                if changed!=wanted or restored!=state:raise ValueError('Wrong or unrestored ownership mutation')
                faults+=1
    if (faults,executing,empty)!=(9,18,12) or reasons!={6,7,9}:raise ValueError('Incomplete wrapper coverage')
    return {'completed':True,'qualified':False,'timestampedOutputExactlyEqual':True,'executingWrapperObservations':executing,
            'emptyFrameObservations':empty,'deletionFlagMutationsDetectedAndRestored':faults,'callbackReasons':sorted(reasons),
            'scope':'Standalone delayed/read-write/read-only callbacks linked to live executing generic wrappers. Deletion ownership observed and restored before return; canceled callbacks never execute.',
            'notEstablished':['Board integration and long-window controls','Other generic objects, initialization families and scheduler continuation','Freed-storage equivalence or general rollback']}


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime build')
    for ext in ('c','v'):shutil.copyfile(HERE/f'fixtures/executing_wrapper_probe.{ext}',out/f'probe.{ext}')
    subprocess.run(['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],check=True)
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    subprocess.run(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')],check=True)
    nm=subprocess.check_output(['nm','-an',str(out/'probe.vpi')],text=True);(out/'probe.vpi.nm').write_text(nm)
    (out/'symbols.json').write_text(json.dumps({'path':str(out/'probe.vpi'),'sha256':sha(out/'probe.vpi'),'offset':symbols(nm)['callback']},indent=2)+'\n')
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};commands={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_WRAPPER_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];commands[name]=cmd
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr);r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Changed runtime')
    result=review(out);result.update(runtime=pins,commands=commands,candidateBuildSha256=sha(candidate/'build.json'))
    shutil.copyfile(candidate/'build.json',out/'build.json');(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'assessment.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        result=review(a.check);retained=json.loads((a.check/'assessment.json').read_text())
        if any(retained.get(k)!=v for k,v in result.items()):raise ValueError('Changed assessment')
        print('Executing wrapper controls verified; board and general rollback remain open.')
    else:
        if any(v is None for v in (a.candidate,a.baseline,a.modules,a.out)):p.error('Need candidate, baseline, modules and out')
        run(a.candidate,a.baseline,a.modules,a.out)
