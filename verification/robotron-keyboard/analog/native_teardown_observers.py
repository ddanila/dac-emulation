#!/usr/bin/env python3
"""Exercise seven populated native observer inventories before native final cleanup under AddressSanitizer."""
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
    shutil.copyfile(HERE/'fixtures/native_teardown_observers.cc',out/'probe.cc')
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
    result=review(out)
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

def review(out):
    receipt=json.loads((out/'run.json').read_text());runs=receipt['runs']
    if set(runs)!={'baseline','disabled','enabled'}:raise ValueError('Missing execution mode')
    bodies={}
    for mode in runs:
        if runs[mode]['exitCode'] or (out/(mode+'.stderr')).read_text():raise ValueError('Abnormal native execution')
        bodies[mode]=(out/(mode+'.stdout')).read_text()
    blocks=re.findall(r'OBSERVER_BEGIN (\d+) (\w+)\n(.*?)OBSERVER_END\n',bodies['enabled'],re.S)
    names={'robotron_vvp_'+n+'_inventory' for n in ('scope_metadata','scope_metadata_reference','parameter','memory_metadata','array','array_compact','port_payload')}
    if len(blocks)!=14 or {n for _,n,_ in blocks}!=names or {r for r,_,_ in blocks}!={'11','12'}:raise ValueError('Incomplete observer coverage')
    for reason in {r for r,_,_ in blocks}:
        if {n for r,n,_ in blocks if r==reason}!=names:raise ValueError('Missing phase inventory')
    from scope_metadata_records import parse as parse_scope
    from scope_metadata_bindings import reference_parse
    from parameter_payload import parse as parse_parameter
    from memory_metadata import parse as parse_memory
    from array_probe import parse as parse_array,validate as validate_array
    from array_compact_probe import expand
    from port_payload import parse as parse_port
    for reason,tick in [('11',0),('12',5000)]:
        images={n.removeprefix('robotron_vvp_').removesuffix('_inventory'):p.splitlines() for r,n,p in blocks if r==reason}
        scope=parse_scope(images['scope_metadata']);refs=reference_parse(images['scope_metadata_reference'])
        parameters=parse_parameter(images['parameter']);memory=parse_memory(images['memory_metadata'])
        arrays=parse_array(images['array']);validate_array(arrays);ports=parse_port(images['port_payload'])
        if expand(images['array_compact'])!=images['array']:raise ValueError('Dense/compact memory mismatch')
        if any(x['tick']!=tick for x in (scope,refs,parameters,memory,arrays,ports)):raise ValueError('Wrong observation time')
        if len(scope['scopes'])!=4 or len(parameters['rows'])!=6 or len(memory['rows'])!=2 or len(arrays['arrays'])!=2 or len(arrays['ports'])!=2 or len(ports['ports'])!=4:raise ValueError('Wrong fixture population')
        scope_pointers={r['id']:r['pointer'] for r in refs['scopes']}
        objects={r['id']:(r['pointer'],r['type']) for r in refs['objects']}
        owners={item['id']:scope_pointers[row['id']] for row in scope['scopes'] for item in row['intern']}
        for row in parameters['rows']:
            if objects.get(row['id'])!=(row['pointer'],41) or owners.get(row['id'])!=row['scope']:raise ValueError('Unbound parameter')
        for row in memory['rows']:
            if objects.get(row['id'])!=(row['handle'],29) or owners.get(row['id'])!=row['scope']:raise ValueError('Unbound memory')
        if {a['key'] for a in arrays['arrays']}!={m['array'] for m in memory['rows']}:raise ValueError('Unbound array')
    cleaned=re.sub(r'OBSERVER_BEGIN \d+ \w+\n.*?OBSERVER_END\n','',bodies['enabled'],flags=re.S)
    if bodies['baseline']!=bodies['disabled'] or cleaned!=bodies['baseline'] or 'CONTINUE ' not in cleaned:raise ValueError('Changed HDL continuation')
    return dict(qualified=False,controlsPassed=True,nativeInventories=7,inventoryImages=14,stdoutExactlyEqual=True,
                scope='Seven inventories execute at start and end of simulation, followed by native final cleanup in the ASAN candidate. Baseline, disabled and enabled HDL output is identical and all exit cleanly. The fixed VPI loader table alone is excluded from ASAN global instrumentation to avoid intentional duplicate-symbol diagnostics. No leak detection, Valgrind annotations, custom-pool safety, destructor-by-destructor proof or board teardown qualification.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('candidate','baseline','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.candidate,a.baseline,a.out)
