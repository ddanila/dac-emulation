#!/usr/bin/env python3
"""Preserve native early/late callback-family refusals through compact observation."""
import argparse,json,os,platform,shutil,subprocess,tempfile
from pathlib import Path
from callback_list_families import FAMILIES,review as dense_review
from callback_delta import separate
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    stats=dict(images=0,denseBytes=0,deltaBytes=0,referenceBytes=0,refusals=0)
    with tempfile.TemporaryDirectory() as tmp:
        copy=Path(tmp);shutil.copy2(root/'run.json',copy/'run.json')
        for family in FAMILIES:
            for timing in ('early','late'):
                for mode in ('original','disabled','observe'):
                    name=f'{family}-{timing}-{mode}';lines,s=separate((root/(name+'.stdout')).read_text().splitlines())
                    if s['refusals']!=lines.count('FAM_REFUSED_EMPTY'):raise ValueError('Missing compact family refusal')
                    for k,v in s.items():stats[k]+=v
                    (copy/(name+'.stdout')).write_text('\n'.join(lines)+'\n');shutil.copy2(root/(name+'.stderr'),copy/(name+'.stderr'))
        result=dense_review(copy)
    if stats['refusals']!=result['refusals'] or stats['images']!=result['admissions']:raise ValueError('Incomplete compact family lifecycle')
    return dict(qualified=False,controlsPassed=True,denseControls=result,compact=stats,scope='Native stateful callback and unknown-owner subclasses introduced before or after compact reference admission. Both reference initialization and later differences refuse before output until native deletion/destruction. Admitted frames reconstruct complete dense lists exactly and original callback continuation remains unchanged.',notEstablished=['Native admitted-owner allocation/removal through compact APIs','Deep typed referents and combined operational integration','Suspended traversal and general rollback'])

def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed runtime')
    shutil.copy2(HERE/'fixtures/callback_list_families.v',out/'probe.v')
    source=(HERE/'fixtures/callback_list_families.cc').read_text()
    marker='int result=api(f);if(fclose(f))exit(2);'
    if source.count(marker)!=1:raise ValueError('Changed native family observation boundary')
    source=source.replace(marker,marker+'compact_check(result);')
    (out/'probe.cc').write_text((HERE/'fixtures/callback_delta_adapter.h').read_text()+'\n'+source)
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
    (out/'run.json').write_text(json.dumps(dict(commands=commands,runs=runs,dependencies=pins,sources={n:sha(HERE/n) for n in ('callback_delta_families.py','callback_delta.py','fixtures/callback_delta_adapter.h','callback_list_families.py','callback_list_probe.py','net_probe.py','net_types_probe.py','fixtures/callback_list_families.cc','fixtures/callback_list_families.v')}),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Compact callback family admission controls verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
