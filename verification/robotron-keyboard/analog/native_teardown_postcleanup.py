#!/usr/bin/env python3
"""Capture post-cleanup observer reads during VPI unload under AddressSanitizer."""
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
    from native_teardown_observers import review as before_cleanup_review
    observed=(out/'enabled.stdout').read_text()
    names=['robotron_vvp_'+n+'_inventory' for n in ('scope_metadata','scope_metadata_reference','parameter','memory_metadata','array','array_compact','port_payload')]
    suffix='POST_CLEANUP_ENTER\n'+''.join('POST_RESULT '+name+' -1 0\n' for name in names)+'POST_CLEANUP_RETURN\n'
    if not observed.endswith(suffix) or observed.count('POST_CLEANUP_ENTER')!=1:raise ValueError('Missing exact post-cleanup refusals')
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        for name in ('run.json','baseline.stdout','baseline.stderr','disabled.stdout','disabled.stderr','enabled.stderr'):
            shutil.copyfile(out/name,root/name)
        (root/'enabled.stdout').write_text(observed[:-len(suffix)])
        before=before_cleanup_review(root)
    return dict(qualified=False,controlsPassed=True,nativeInventories=before['nativeInventories'],inventoryImages=before['inventoryImages'],
                postCleanupZeroOutputRefusals=7,stdoutExactlyEqual=True,
                scope='Seven populated inventories safely refuse after native final cleanup during VPI unload, each returning -1 with zero output. Baseline/disabled/enabled HDL output matches and exits are clean. Fixed fixture loader-table global instrumentation is excluded; runtime memory checks remain enabled. No proof of empty registries, individual destructor coverage, dangling-handle safety, custom-pool safety, leaks or board teardown.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.out)
