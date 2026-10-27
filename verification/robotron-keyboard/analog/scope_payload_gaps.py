#!/usr/bin/env python3
"""Replay scope-owned signal, parameter and memory payload counterexamples."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from scope_metadata_records import parse as metadata_parse
from scope_metadata_bindings import reference_parse
from signal_handles import parse as signal_parse
from port_payload import parse as port_parse
from array_probe import parse as array_parse
HERE=Path(__file__).resolve().parent


def parse(lines):
    result={};i=0
    for tag,parser in (('VSM',metadata_parse),('VSMR',reference_parse),('VSH',signal_parse),('VPP',port_parse),('VAR',array_parse)):
        if i>=len(lines) or not lines[i].startswith(tag+'_BEGIN '):raise ValueError('Missing payload-gap image section')
        j=next((j for j in range(i,len(lines)) if lines[j].startswith(tag+'_END ')),None)
        if j is None:raise ValueError('Truncated payload-gap image section')
        result[tag]=parser(lines[i:j+1]);i=j+1
    if i!=len(lines):raise ValueError('Trailing gap image records')
    return result


def review(root):
    receipt=json.loads((root/'run.json').read_text());images={}
    expected=[]
    for r in (1,2):expected += [f'ROUND {r}','SIGNAL -6 10','PARAMETER 3 2','MEMORY memory Xemory',f'RESTORED {r}']
    expected += ['CONTINUE -6 -6 3 5','finish']
    for mode in ('baseline','disabled','enabled'):
        if receipt['runs'][mode]['exitCode'] or (root/(mode+'.stderr')).read_text():raise ValueError('Failed native gap control')
        lines=(root/(mode+'.stdout')).read_text().splitlines();i=0;events=[]
        while i<len(lines):
            line=lines[i];i+=1
            if line.startswith('IMAGE '):
                key=line.split()[1];start=i
                while i<len(lines) and lines[i]!='IMAGE_END':i+=1
                if i==len(lines) or key in images or mode!='enabled':raise ValueError('Invalid gap witness image')
                images[key]=lines[start:i];parse(images[key]);i+=1
            else:events.append('finish' if '$finish called at 3000 (1ps)' in line else line)
        if events!=expected:raise ValueError('Changed consumer results or continuation')
    if set(images)!={f'{kind}{r}' for r in (1,2) for kind in ('before','signal','parameter','memory','restored')}:raise ValueError('Missing gap controls')
    for r in (1,2):
        before=images[f'before{r}'];state=parse(before)
        if state['VSM']['tick']!=r*1000 or len(state['VSH']['rows'])!=1:raise ValueError('Wrong observation scope')
        if any(images[f'{kind}{r}']!=before for kind in ('signal','parameter','memory','restored')):raise ValueError('Expected invisible mutation changed image')
    return dict(qualified=False,controlsPassed=True,rounds=2,originalContinuationExactlyEqual=True,
        invisibleFields=['unadmittedSignalSignedness','binaryParameterBits','memoryName'],
        unchangedImages=['scopeMetadata','scopeObjectReferences','admittedSignalHandles','portPayloads','arrayPayloads'],
        scope='Restored diagnostic mutations change native VPI results while five complete existing observer images remain byte-identical. Only one of two fixture signal handles is explicitly admitted. No ordinary board mutation, complete combined-state comparison, parameter observer or general lifecycle qualification is implied.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for ext in ('cc','v'):shutil.copy2(HERE/f'fixtures/scope_payload_gaps.{ext}',out/f'probe.{ext}')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands=[['iverilog','-g2012','-ginterconnect','-o',str(out/'probe.vvp'),str(out/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for cmd in commands:subprocess.run(cmd,check=True)
    pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'probe.vvp',*modules.glob('*.vpi')]};runs={}
    for mode in ('baseline','disabled','enabled'):
        lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so'
        env=dict(os.environ,K7658_PORT_PAYLOAD='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(r.stdout);(out/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n')
    (out/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
