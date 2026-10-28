#!/usr/bin/env python3
"""Isolate native single-stream inventory behavior before and after final cleanup."""
import argparse,json,os,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def run(candidate,baseline,out):
    candidate=candidate.resolve();baseline=baseline.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    if any(sha(candidate/n)!=h for n,h in build['outputs'].items()):raise ValueError('Changed native build')
    sources={};names=set()
    pattern=r'extern\s+"C"\s+int\s+(robotron_vvp_\w*inventory)\s*\(\s*FILE\s*\*\s*\w*\s*\)\s*\{'
    for path in sorted((candidate/'vvp').glob('*.cc')):
        found=re.findall(pattern,path.read_text())
        if found:sources[str(path.relative_to(candidate))]=sha(path);names.update(found)
    if not names:raise ValueError('No single-stream inventory definitions')
    names.update(('robotron_vvp_code_operand_inventory','robotron_vvp_sync_inventory','robotron_vvp_sync_family_inventory'))
    sources['vvp/codes.cc']=sha(candidate/'vvp/codes.cc')
    shutil.copyfile(HERE/'fixtures/native_teardown.v',out/'probe.v');shutil.copyfile(HERE/'fixtures/native_observer_shutdown_sweep.cc',out/'probe.cc')
    commands=[['iverilog','-g2012','-o',str(out/'baseline.vvp'),str(out/'probe.v')],['c++','-std=c++11','-fsanitize=address','-bundle','-undefined','dynamic_lookup','-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]]
    for command in commands:subprocess.run(command,check=True)
    compiled=(out/'baseline.vvp').read_text();modules=[Path(json.loads(line[len(':vpi_module '):-1])) for line in compiled.splitlines() if line.startswith(':vpi_module ')]
    system=[p for p in modules if p.name=='system.vpi']
    if len(system)!=1:raise ValueError('Ambiguous system module')
    (out/'candidate.vvp').write_text(compiled.replace(str(system[0]),str(candidate/'vpi/system.vpi')))
    pins={str(p):sha(p) for p in [baseline/'vvp/libvvp.so',candidate/'vvp/vvp',candidate/'vvp/libvvp.so',candidate/'vpi/system.vpi',out/'probe.vpi',*modules]};runs={}
    for mode in ['baseline','disabled',*sorted(names)]:
        root=baseline if mode=='baseline' else candidate
        env=dict(os.environ,DYLD_LIBRARY_PATH=str(root/'vvp'),ASAN_OPTIONS='halt_on_error=1:abort_on_error=0:detect_leaks=0',TEARDOWN_INVENTORY='off' if mode in ('baseline','disabled') else mode)
        env.pop('ROBOTRON_TEARDOWN_TRACE',None)
        command=[str(candidate/'vvp/vvp'),'-M'+str(out),'-mprobe',str(out/('baseline.vvp' if mode=='baseline' else 'candidate.vvp'))]
        result=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(mode+'.stdout')).write_text(result.stdout);(out/(mode+'.stderr')).write_text(result.stderr)
        runs[mode]=dict(exitCode=result.returncode,command=command,asanOptions=env['ASAN_OPTIONS'],inventory=env['TEARDOWN_INVENTORY'])
    if any(sha(Path(p))!=h for p,h in pins.items()) or any(sha(candidate/p)!=h for p,h in sources.items()):raise ValueError('Changed sweep dependency')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n');(out/'run.json').write_text(json.dumps(dict(commands=commands,dependencies=pins,inventorySources=sources,inventories=sorted(names),runs=runs),indent=2)+'\n')
    result=review(out);(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

def review(root):
    receipt=json.loads((root/'run.json').read_text());runs=receipt['runs'];names=receipt['inventories']
    if set(runs)!={'baseline','disabled',*names}:raise ValueError('Missing sweep process')
    original=(root/'baseline.stdout').read_text()
    for mode in ('baseline','disabled'):
        if runs[mode]['exitCode'] or (root/(mode+'.stderr')).read_text() or (root/(mode+'.stdout')).read_text()!=original:raise ValueError('Failed sweep reference')
    if 'CONTINUE ' not in original:raise ValueError('Missing reference continuation')
    results={}
    for name in names:
        text=(root/(name+'.stdout')).read_text();errors=(root/(name+'.stderr')).read_text()
        if runs[name].get('inventory')!=name:raise ValueError('Wrong selected inventory')
        frames=re.findall(r'SWEEP_ENTER (start|end|post)\nSWEEP_RESULT \1 (-?\d+) (\d+)\n(.*?)SWEEP_END \1\n',text,re.S)
        if len({p for p,_,_,_ in frames})!=len(frames) or not {'start','end'}<={p for p,_,_,_ in frames}:raise ValueError('Incomplete pre-cleanup observation')
        for phase,rc,size,payload in frames:
            if len(payload.encode())!=int(size) or (int(rc)<0 and int(size)):raise ValueError('Incorrect inventory byte count/refusal')
        cleaned=re.sub(r'SWEEP_ENTER (start|end|post)\nSWEEP_RESULT \1 (-?\d+) (\d+)\n.*?SWEEP_END \1\n','',text,flags=re.S).replace('SWEEP_ADMITTED 3\n','').removesuffix('SWEEP_ENTER post\n')
        if cleaned!=original or text.count('SWEEP_ADMITTED 3\n')!=1:raise ValueError('Changed sweep HDL continuation')
        phases={phase:dict(returnCode=int(rc),bytes=int(size)) for phase,rc,size in re.findall(r'^SWEEP_RESULT (start|end|post) (-?\d+) (\d+)$',text,re.M)}
        results[name]=dict(exitCode=runs[name]['exitCode'],phases=phases,postEntered='SWEEP_ENTER post\n' in text,postReturned='SWEEP_END post\n' in text,addressSanitizerError='ERROR: AddressSanitizer:' in errors,stderrEmpty=not errors)
    return dict(qualified=False,controlsPassed=False,inventories=len(names),sanitizerFailures=sum(r['addressSanitizerError'] for r in results.values()),postRefusals=sum(r['phases'].get('post')==dict(returnCode=-1,bytes=0) for r in results.values()),postAcceptances=sum(r['phases'].get('post',{}).get('returnCode')==0 for r in results.values()),results=results,scope='Diagnostic sweep of 52 single-stream and three explicitly adapted multi-argument inventory APIs on one hierarchical fixture with three admitted signal handles. Each API runs in a separate process at simulation start/end and VPI unload. Refusal, empty acceptance and sanitizer failures are recorded without general lifecycle acceptance. Code operands use dense mode; sync-family identities are null, and the legacy sync API intentionally refuses. Unpopulated families remain outside payload coverage; ASAN loader-table exclusions and disabled leak/custom-pool checks remain.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.out)
