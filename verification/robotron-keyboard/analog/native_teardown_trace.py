#!/usr/bin/env python3
"""Trace native destruction and post-cleanup registry sizes under AddressSanitizer."""
import argparse,json,os,platform,re,shutil,subprocess,tempfile
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def run(candidate,baseline,out):
    candidate=candidate.resolve();baseline=baseline.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    if any(sha(candidate/n)!=h for n,h in build['outputs'].items()):raise ValueError('Changed candidate build')
    if not re.search(r'^#\s*define\s+CHECK_WITH_VALGRIND\s+1\s*$',(candidate/'config.h').read_text(),re.M):raise ValueError('Native cleanup is disabled')
    shutil.copyfile(HERE/'fixtures/native_teardown.v',out/'probe.v')
    command=['iverilog','-g2012','-o',str(out/'baseline.vvp'),str(out/'probe.v')];subprocess.run(command,check=True)
    shutil.copyfile(HERE/'fixtures/native_teardown_postcleanup.cc',out/'probe.cc')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    compile_observer=['c++','-std=c++11','-fsanitize=address',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.cc')]
    subprocess.run(compile_observer,check=True)
    compiled=(out/'baseline.vvp').read_text();modules=[]
    for line in compiled.splitlines():
        if line.startswith(':vpi_module '):modules.append(Path(json.loads(line[len(':vpi_module '):-1])))
    system=[p for p in modules if p.name=='system.vpi']
    if len(system)!=1:raise ValueError('Ambiguous system module')
    modified=compiled.replace(str(system[0]),str(candidate/'vpi/system.vpi'));(out/'teardown.vvp').write_text(modified)
    pins={str(p):sha(p) for p in [baseline/'vvp/libvvp.so',candidate/'vvp/vvp',candidate/'vvp/libvvp.so',candidate/'vpi/system.vpi',out/'probe.vpi',*modules]}
    runs={}
    for mode,root in [('baseline',baseline),('disabled',candidate),('enabled',candidate)]:
        env=os.environ.copy();env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(root/'vvp')
        env['ASAN_OPTIONS']='halt_on_error=1:abort_on_error=0:detect_leaks=0'
        env['TEARDOWN_OBSERVE']='on' if mode=='enabled' else 'off'
        env.pop('ROBOTRON_TEARDOWN_TRACE',None)
        if mode=='enabled':env['ROBOTRON_TEARDOWN_TRACE']='1'
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(out),'-mprobe',str(out/('baseline.vvp' if mode=='baseline' else 'teardown.vvp'))]
        result=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=60)
        (out/(mode+'.stdout')).write_text(result.stdout);(out/(mode+'.stderr')).write_text(result.stderr)
        runs[mode]=dict(command=cmd,exitCode=result.returncode,asanOptions=env['ASAN_OPTIONS'])
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Changed runtime dependency')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n');(out/'run.json').write_text(json.dumps(dict(compileCommand=command,observerCompileCommand=compile_observer,runs=runs,dependencies=pins),indent=2)+'\n')
    try: result=review(out)
    except ValueError as error:
        result=dict(qualified=False,controlsPassed=False,error=str(error),postCleanupEntered='POST_CLEANUP_ENTER' in (out/'enabled.stdout').read_text(),addressSanitizerError='ERROR: AddressSanitizer:' in (out/'enabled.stderr').read_text(),scope='Diagnostic post-cleanup observer access. Failure remains a refusal/teardown gap; no qualification is claimed.')
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

def review(out):
    from native_teardown_postcleanup import review as post_review
    from parameter_payload import parse as parse_parameter
    from memory_metadata import parse as parse_memory
    observed=(out/'enabled.stdout').read_text();lines=observed.splitlines()
    trace=[line for line in lines if line.startswith('TEARDOWN_')]
    if not trace or trace[0]!='TEARDOWN_BEGIN' or trace[-1]!='TEARDOWN_UNLOAD':raise ValueError('Missing native cleanup trace')
    images=re.findall(r'OBSERVER_BEGIN 12 (\w+)\n(.*?)OBSERVER_END\n',observed,re.S)
    images=dict(images)
    parameters=parse_parameter(images['robotron_vvp_parameter_inventory'].splitlines())['rows']
    memory=parse_memory(images['robotron_vvp_memory_metadata_inventory'].splitlines())['rows']
    destroyed=[line.split() for line in trace if line.startswith('TEARDOWN_PARAMETER ')]
    if len(destroyed)!=6 or {(int(p,16),k.lower()) for _,k,p in destroyed}!={(r['pointer'],r['kind']) for r in parameters}:raise ValueError('Missing native parameter destruction')
    remaining=[int(line.split()[1]) for line in trace if line.startswith('TEARDOWN_PARAMETER_REMAIN ')]
    if remaining!=[5,4,3,2,1,0]:raise ValueError('Parameter registry not drained')
    memories=[line.split() for line in trace if line.startswith('TEARDOWN_MEMORY ')]
    if len(memories)!=2 or {int(p,16) for _,p,_ in memories}!={r['array'] for r in memory} or [int(n) for _,_,n in memories]!=[1,0]:raise ValueError('Missing native memory destruction')
    registry=[line.split() for line in trace if line.startswith('TEARDOWN_REGISTRIES ')]
    if len(registry)!=2 or [r[1] for r in registry]!=['before','after'] or any(len(r)!=11 for r in registry) or len(trace)!=18:raise ValueError('Incomplete registry trace')
    keys=['roots','initializedScopes','scopeMetadata','attachedObjects','objectIds','objectTypes','ports','portSlots','portBits']
    sizes={r[1]:dict(zip(keys,map(int,r[2:]))) for r in registry}
    if sizes['before']['roots']!=2 or sizes['after']['roots']!=0:raise ValueError('Native roots were not cleared')
    if lines.index('TEARDOWN_BEGIN')<max(i for i,line in enumerate(lines) if line=='OBSERVER_END') or lines.index('TEARDOWN_UNLOAD')>lines.index('POST_CLEANUP_ENTER'):raise ValueError('Wrong cleanup phase ordering')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        for name in ('run.json','baseline.stdout','baseline.stderr','disabled.stdout','disabled.stderr','enabled.stderr'):
            shutil.copyfile(out/name,root/name)
        (root/'enabled.stdout').write_text(''.join(line+'\n' for line in lines if not line.startswith('TEARDOWN_')))
        post_review(root)
    return dict(qualified=False,controlsPassed=True,nativeParameterDestructions=6,nativeMemoryDestructions=2,
                registrySizes=sizes,allTrackedRegistriesEmpty=not any(sizes['after'].values()),postCleanupZeroOutputRefusals=7,
                scope='Diagnostic-only instrumentation proves six parameter and two memory destructor entries, corresponding registry drainage, and native root cleanup. Remaining registry counts are reported without a teardown acceptance waiver. ASAN limitations and loader-table exclusion remain those of the post-cleanup fixture; full board and dangling-handle safety remain unqualified.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.out)
