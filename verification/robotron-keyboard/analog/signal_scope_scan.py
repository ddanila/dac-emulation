#!/usr/bin/env python3
"""Differential native replay for one complete scope scan per signal snapshot."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
import signal_handle_families,typed_signal_fault_native
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
CASES={'families':'signal_handle_families','faults':'typed_signal_faults','automatic':'signal_scope_admission'}


def strip(text):
    lines=[];counts={'signals':{'success':0,'refused':0},'links':{'success':0,'refused':0}}
    for line in text.splitlines():
        if not line.startswith('SCOPE_EQ '):lines.append(line);continue
        a=line.split()
        if len(a)!=4 or a[1] not in counts or a[2] not in ('0','-1'):raise ValueError('Invalid scope comparison marker')
        size=int(a[3]);success=a[2]=='0'
        if size<0 or success and size==0 or not success and size!=0:raise ValueError('Partial native scope output')
        counts[a[1]]['success' if success else 'refused']+=1
    return '\n'.join(lines)+'\n',counts


def review(root):
    results={}
    for case in CASES:
        folder=root/case;counts=None
        with tempfile.TemporaryDirectory() as tmp:
            filtered=Path(tmp);shutil.copy2(folder/'run.json',filtered/'run.json')
            for mode in ('baseline','disabled','enabled'):
                text,got=strip((folder/(mode+'.stdout')).read_text())
                if mode!='enabled' and any(sum(v.values()) for v in got.values()):raise ValueError('Original/disabled unexpectedly observed')
                if mode=='enabled':counts=got
                (filtered/(mode+'.stdout')).write_text(text);shutil.copy2(folder/(mode+'.stderr'),filtered/(mode+'.stderr'))
            if case=='families':result=signal_handle_families.review(filtered)
            elif case=='faults':result=typed_signal_fault_native.review(filtered)
            else:
                receipt=json.loads((filtered/'run.json').read_text())
                for mode in ('baseline','disabled','enabled'):
                    lines=(filtered/(mode+'.stdout')).read_text().splitlines()
                    if receipt['runs'][mode]['exitCode'] or (filtered/(mode+'.stderr')).read_text() or len(lines)!=3 or lines[:2]!=['SCOPE_ADMISSION_DONE','CONTINUE 1'] or '$finish called at 2000 (1ps)' not in lines[-1]:raise ValueError('Automatic-scope behavior changed')
                result={'controlsPassed':True,'emptyAdmissionPreserved':True,'automaticScopeRefusedAfterHandoff':True}
        if case=='families' and (not counts['signals']['success'] or counts['signals']['refused']):raise ValueError('Missing supported family comparisons')
        if case=='faults' and any(not counts[k][v] for k,v in [('signals','success'),('links','success'),('links','refused')]):raise ValueError('Missing native fault differential')
        if case=='automatic' and counts['signals']!={'success':1,'refused':1}:raise ValueError('Missing empty/automatic scope controls')
        results[case]=dict(comparisons=counts,originalControls=result)
    return dict(qualified=False,controlsPassed=True,cases=results,scope='Optimized and reference native inventories produce identical complete bytes and return codes in the same process, including metadata faults, restored lifetimes, active callbacks, range/cache growth and rejected automatic scopes. Empty admission still emits an empty image even with an automatic scope. This establishes differential controls, not operational cost or whole-board qualification.')


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed runtime')
    for case,fixture in CASES.items():
        folder=out/case;folder.mkdir();source=(HERE/f'fixtures/{fixture}.cc').read_text()
        if case!='automatic':
            anchor='#include "vpi_priv.h"';assert anchor in source;source=source.replace(anchor,anchor+'\n#include "scope_compare.h"')
        (folder/'probe.cc').write_text(source);shutil.copy2(HERE/f'fixtures/{fixture}.v',folder/'probe.v');shutil.copy2(HERE/'fixtures/signal_scope_scan_adapter.h',folder/'scope_compare.h')
        flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
        commands=[['iverilog','-g2012','-o',str(folder/'probe.vvp'),str(folder/'probe.v')],['c++','-std=c++11',*flags,'-I'+str(candidate),'-I'+str(candidate/'vvp'),'-o',str(folder/'probe.vpi'),str(folder/'probe.cc')]]
        for cmd in commands:subprocess.run(cmd,check=True)
        pins={str(p):sha(p) for p in [baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',folder/'probe.vpi',folder/'probe.vvp',*modules.glob('*.vpi')]};runs={}
        for mode in ('baseline','disabled','enabled'):
            lib=baseline if mode=='baseline' else candidate/'vvp/libvvp.so';env=dict(os.environ,K7658_REFERENTS='on' if mode=='enabled' else 'off');env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
            cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp'];r=subprocess.run(cmd,cwd=folder,env=env,capture_output=True,text=True,timeout=30)
            (folder/(mode+'.stdout')).write_text(r.stdout);(folder/(mode+'.stderr')).write_text(r.stderr);runs[mode]=dict(exitCode=r.returncode,command=cmd,library=str(lib));r.check_returncode()
        if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Dependencies changed')
        (folder/'run.json').write_text(json.dumps(dict(runs=runs,commands=commands,dependencies=pins),indent=2)+'\n')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n');(out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.modules,a.out)
