#!/usr/bin/env python3
"""Capture native final-cleanup diagnostics under AddressSanitizer without claiming Valgrind coverage."""
import argparse,json,os,platform,re,shutil,subprocess
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
    compiled=(out/'baseline.vvp').read_text();modules=[]
    for line in compiled.splitlines():
        if line.startswith(':vpi_module '):modules.append(Path(json.loads(line[len(':vpi_module '):-1])))
    system=[p for p in modules if p.name=='system.vpi']
    if len(system)!=1:raise ValueError('Ambiguous system module')
    modified=compiled.replace(str(system[0]),str(candidate/'vpi/system.vpi'));(out/'teardown.vvp').write_text(modified)
    pins={str(p):sha(p) for p in [baseline/'vvp/libvvp.so',candidate/'vvp/vvp',candidate/'vvp/libvvp.so',candidate/'vpi/system.vpi',*modules]}
    runs={}
    for mode,root in [('baseline',baseline),('teardown',candidate)]:
        env=os.environ.copy();env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(root/'vvp')
        env['ASAN_OPTIONS']='halt_on_error=1:abort_on_error=0:detect_leaks=0'
        cmd=[str(candidate/'vvp/vvp'),str(out/(mode+'.vvp'))]
        result=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=60)
        (out/(mode+'.stdout')).write_text(result.stdout);(out/(mode+'.stderr')).write_text(result.stderr)
        runs[mode]=dict(command=cmd,exitCode=result.returncode,asanOptions=env['ASAN_OPTIONS'])
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Changed runtime dependency')
    (out/'build.json').write_text(json.dumps(build,indent=2)+'\n');(out/'run.json').write_text(json.dumps(dict(compileCommand=command,runs=runs,dependencies=pins),indent=2)+'\n')
    original=(out/'baseline.stdout').read_text();observed=(out/'teardown.stdout').read_text();errors=(out/'teardown.stderr').read_text()
    result=dict(qualified=False,controlsPassed=not runs['baseline']['exitCode'] and not runs['teardown']['exitCode'] and not errors and not (out/'baseline.stderr').read_text() and 'CONTINUE ' in original and observed==original,
                baselineExitCode=runs['baseline']['exitCode'],teardownExitCode=runs['teardown']['exitCode'],stdoutExactlyEqual=observed==original,addressSanitizerError='ERROR: AddressSanitizer:' in errors,
                scope='Native final cleanup is enabled in an AddressSanitizer-instrumented candidate. Valgrind annotations and leak detection are explicitly disabled. A hierarchical static-memory/parameter/read-port/monitor fixture exercises normal execution and shutdown. Any diagnostic or abnormal exit prevents qualification; absence of diagnostics alone does not prove general graph teardown or custom-pool memory safety.')
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.out)
