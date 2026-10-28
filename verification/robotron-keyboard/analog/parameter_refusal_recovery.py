#!/usr/bin/env python3
"""Recover native observation after deleting late unsupported parameter subclasses."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from parameter_payload import parse
HERE=Path(__file__).resolve().parent
FAMILIES=('binary','real','string')


def review(root):
    import struct
    from parameter_lifecycle import parse_image
    receipt=json.loads((root/'run.json').read_text());images={}
    if set(receipt['runs'])!={f+'-'+m for f in FAMILIES for m in ('baseline','disabled','enabled')}:raise ValueError('Missing recovery comparisons')
    for kind,family in enumerate(FAMILIES):
        for mode in ('baseline','disabled','enabled'):
            key=family+'-'+mode;r=receipt['runs'][key]
            if r['exitCode'] or r['family']!=family or r['observer']!=mode or (root/(key+'.stderr')).read_text():raise ValueError('Native recovery failed')
            lines=(root/(key+'.stdout')).read_text().splitlines();i=0;events=[]
            while i<len(lines):
                line=lines[i];i+=1
                if line.startswith('IMAGE '):
                    label=(family,line.split()[1]);start=i
                    while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                    if i==len(lines) or mode!='enabled' or label in images:raise ValueError('Invalid recovery image')
                    images[label]=lines[start:i];parse_image(images[label]);i+=1
                else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
            expected=[]
            for n in (1,2):
                expected.append(f'ROUND {n}')
                if mode!='baseline':
                    expected.append(f'UNSUPPORTED {n} {kind}')
                    if mode=='enabled':expected += [f'REFUSED {n}',f'STALE_REFUSED {n} 0 3']
                    expected.append(f'SUPPORTED {n} {kind}')
                    if mode=='enabled':expected.append(f'STALE_REFUSED {n} 1 3')
            if events!=expected+['CONTINUE 3 123456789abcdef01234 1.5','finish']:raise ValueError('Missing recovery/refusal or changed continuation')
    if set(images)!={(family,f'{phase}{n}') for family in FAMILIES for phase in ('before','recovered','supported','restored') for n in (1,2)}:raise ValueError('Missing recovery inventories')
    for kind,family in enumerate(FAMILIES):
        last_id=0
        for n in (1,2):
            before=images[family,f'before{n}'];base=parse_image(before)
            if base['tick']!=n*1000 or len(base['rows'])!=4:raise ValueError('Wrong recovery baseline')
            if images[family,f'recovered{n}']!=before or images[family,f'restored{n}']!=before:raise ValueError('Incomplete recovery/restoration')
            added=parse_image(images[family,f'supported{n}'])
            if added['tick']!=base['tick'] or len(added['rows'])!=5 or added['rows'][:-1]!=base['rows']:raise ValueError('Changed original parameters')
            row=added['rows'][-1];v=row['value']
            if row['id']<=max(last_id,max(r['id'] for r in base['rows'])) or row['kind']!=family or row['name']!=f'__growth_{kind}_{n}\0'.encode().hex():raise ValueError('Invalid fresh supported parameter')
            last_id=row['id']
            if kind==0:
                mask=(1<<v['wordBits'])-1
                if v['width']!=80 or v['signed'] or v['sized'] or v['words']!=[[mask,mask^1]]+[[mask,mask]]*(v['wordCount']-1):raise ValueError('Wrong recovered binary payload')
            elif kind==1 and v['value']!=struct.pack('=d',2.5).hex():raise ValueError('Wrong recovered real payload')
            elif kind==2 and v['value']!='47005200':raise ValueError('Lost recovered embedded-null string')
    return dict(qualified=False,controlsPassed=True,families=list(FAMILIES),unsupportedDestructions=6,supportedDestructions=6,unsupportedInventoryRefusals=6,staleEntryZeroOutputRefusals=36,exactRecoveryRestorations=12,supportedAllocationsAfterRefusal=6,originalHdlContinuationExactlyEqual=True,scope='Diagnostic unsupported subclasses are deleted through their native virtual destructors and the object allocation is freed. Stale scope entries refuse before dereference; detachment restores all three original inventories. Subsequent exact-class allocation succeeds with full payloads and fresh IDs, then deletion/restoration repeats. Nine original/disabled/enabled runs preserve HDL continuation. No guarantee of allocator address reuse, dangling-handle safety, compiled-reference deletion or full graph teardown.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/parameter_refusal_recovery.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for family in ('binary','real','string'):
        for mode in ('baseline','disabled','enabled'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
            env=dict(os.environ,ROBOTRON_PARAMETER_CLASS='none',K7658_PARAMETER_KIND=str(('binary','real','string').index(family)),K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
            (out/(family+'-'+mode+'.stdout')).write_text(r.stdout);(out/(family+'-'+mode+'.stderr')).write_text(r.stderr);runs[family+'-'+mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib),family=family,observer=mode);r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
