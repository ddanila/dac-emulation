#!/usr/bin/env python3
"""Measure actual initialized bridge callback ownership before HDL advancement."""
import argparse,json,math,shutil,subprocess
from pathlib import Path
from callback_list_probe import parse
from net_probe import pointer
from port_identity_review import snapshot as port_snapshot
from port_board_review import port_contract
from raw_assignment_board_capture import runtime_environment
from eval_cache_benchmark import external_dependencies,verify_dependencies
from ngspice_runtime import verify
from retained_evidence import check
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text())
    if receipt['exitCode']!=0:raise ValueError('Failed actual bridge diagnostic')
    before=(root/'callbacks-before.txt').read_text()
    if before!=(root/'callbacks-after.txt').read_text():raise ValueError('Callback observation changed state')
    state=parse(before.splitlines())
    if state['tick']!=0:raise ValueError('HDL time advanced during initial budget')
    ports=port_snapshot((root/'ports.txt').read_text().splitlines());contract=port_contract((root/'io.vvp').read_text())
    if [{k:p[k] for k in ('direction','bits','name','index','position')} for p in ports['ports']]!=contract:raise ValueError('Bridge ports differ from compiled interface')
    expected=[p['index'] for p in ports['ports'] if p['direction']!=1]
    if not expected or ports['outPending']!=len(expected):raise ValueError('Outputs not fully initialized and seeded')
    callbacks={c['id']:c for o in state['owners'] for c in o['callbacks']};bindings=[]
    for line in (root/'bindings.txt').read_text().splitlines():
        a=line.split()
        if len(a)!=7 or a[0]!='CB_BIND':raise ValueError('Invalid initialized bridge binding')
        index,identity=map(int,a[1:3]);port,handle,signal,function=map(pointer,a[3:])
        cb=callbacks.get(identity)
        if not cb or any(not p for p in (port,handle,signal,function)) or (cb['pointer'],cb['object'],cb['user'],cb['function'])!=(handle,signal,port,function):raise ValueError('Callback fields differ from initialized bridge registration')
        bindings.append((index,identity,port,signal,function))
    if [r[0] for r in bindings]!=expected or len({r[1] for r in bindings})!=len(bindings) or set(callbacks)!={r[1] for r in bindings}:raise ValueError('Incomplete callback-to-port mapping')
    if len({r[2] for r in bindings})!=len(bindings) or len({r[3] for r in bindings})!=len(bindings) or len({r[4] for r in bindings})!=1:raise ValueError('Aliased bridge referents')
    output=(root/'outputs.txt').read_text().splitlines()
    if output!=[f'VW_BEGIN 1 {len(bindings)}']+[f'VW_LINK {i} {identity}' for i,identity,*_ in bindings]+['VW_END']:raise ValueError('Previous output lifetime bindings differ')
    budget=(root/'budget.txt').read_text().splitlines()
    if len(budget)!=3 or budget[1:]!=['CB_UNADMITTED_REFUSED','CB_BUDGET_DONE']:raise ValueError('Incomplete diagnostic or missing admission refusal')
    a=budget[0].split()
    if len(a)!=5 or a[:2]!=['CB_BUDGET','64']:raise ValueError('Invalid scan budget')
    total,minimum,maximum=map(float,a[2:])
    if not all(math.isfinite(x) for x in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum:raise ValueError('Invalid measurements')
    calls=2*receipt['reviewedBoundaries']
    if calls<=0:raise ValueError('Invalid prior boundary count')
    return dict(qualified=False,controlsPassed=True,initializedBridgeCallbacks=len(bindings),owners=len(state['owners']),emptyOwners=sum(not o['callbacks'] and not o['words'] for o in state['owners']),arrayWordAssociations=sum(len(o['words']) for o in state['owners']),listImageBytes=len(before.encode()),scanTimings=dict(iterations=64,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum),initialStateProjection=dict(normalSnapshotCalls=calls,logicalBytes=calls*len(before.encode()),scanSeconds=calls*total/64,excludesStateGrowthCompressionAndOtherObservers=True),scope='Actual compiled keyboard board and real bridge registrations, after port metadata and output seeding but before first coroutine advance. Every callback binds to initialized bridge port/signal/function identity and prior output lifetime records. Native inventory refuses before explicit admission. Complete lists repeat exactly through measured full scans.',notEstablished=['Operational callback/association lifecycle, combined capture and review cost','Deep typed VPI signal metadata and graph owner binding','Suspended native traversal, shared result storage and general rollback'])


def run(source,bridge,icarus,out):
    source=source.resolve();bridge=bridge.resolve();icarus=icarus.resolve();out=out.resolve();check(source)
    assessment=json.loads((source/'assessment.json').read_text());baseline=source/'off';base=json.loads((baseline/'run.json').read_text())
    if not assessment['controlsPassed'] or assessment['receipts']['off']!=sha(baseline/'run.json'):raise ValueError('Need reviewed board source')
    builds={}
    for label,folder in [('bridge',bridge),('icarus',icarus)]:
        r=json.loads((folder/'build.json').read_text())
        for name,digest in r['outputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Changed '+label+' build')
        builds[label]=r
    env=runtime_environment(base);verify_dependencies(base['externalDependencies'])
    for name,digest in base['inputs'].items():
        if sha(baseline/name)!=digest:raise ValueError('Changed board source input')
    def dep(name):
        matches=[d['path'] for d in base['externalDependencies'] if Path(d['path']).name==name]
        if len(matches)!=1:raise ValueError('Ambiguous dependency '+name)
        return matches[0]
    out.mkdir(exist_ok=False);deck=(baseline/'io.cir').read_text()
    for name,new in [('ivlng.so',bridge/'ivlng.so'),('ivlng.vpi',bridge/'ivlng.vpi'),('libvvp.so',icarus/'vvp/libvvp.so')]:
        old=dep(name)
        if deck.count(old)!=1:raise ValueError('Changed dependency placement')
        deck=deck.replace(old,str(new))
    vvp=(baseline/'io.vvp').read_text();old=':vpi_module "'+dep('system.vpi')+'";'
    if vvp.count(old)!=1:raise ValueError('Changed system module placement')
    (out/'io.vvp').write_text(vvp.replace(old,':vpi_module "'+str(icarus/'vpi/system.vpi')+'";'))
    (out/'io.cir').write_text(deck);shutil.copy2(baseline/'s600.hex',out/'s600.hex')
    for label,r in builds.items():(out/(label+'-build.json')).write_text(json.dumps(r,indent=2)+'\n')
    env.update(ROBOTRON_PRIVATE_DISPLAY='off',ROBOTRON_DISPLAY_MODULE=str(icarus/'vpi/system.vpi'))
    deps=external_dependencies(out,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
    input_pins={n:sha(out/n) for n in ('io.cir','io.vvp','s600.hex')}
    cmd=[base['runtime']['executable']['path'],'-n','-b','io.cir'];r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'stdout.txt').write_text(r.stdout);(out/'stderr.txt').write_text(r.stderr)
    verify(base['runtime']);verify_dependencies(deps)
    if any(sha(out/n)!=digest for n,digest in input_pins.items()):raise ValueError('Inputs changed during diagnostic')
    for label,folder in [('bridge',bridge),('icarus',icarus)]:
        for name,digest in builds[label]['outputs'].items():
            if sha(folder/name)!=digest:raise ValueError('Runtime changed during diagnostic')
    (out/'run.json').write_text(json.dumps(dict(exitCode=r.returncode,command=cmd,runtime=base['runtime'],externalDependencies=deps,environment={k:v for k,v in env.items() if k.startswith('ROBOTRON_')},runtimeEnvironment={'SPICE_SCRIPTS':env['SPICE_SCRIPTS']},inputs=input_pins,sourceManifestSha256=sha(source/'manifest.json'),sourceAssessmentSha256=sha(source/'assessment.json'),reviewedBoundaries=assessment['observedState']['boundaries'],producerSha256=sha(Path(__file__))),indent=2)+'\n')
    r.check_returncode();(out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('source','bridge','icarus','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if review(a.check)!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed diagnostic assessment')
        print('Initialized bridge callback bindings and scan budget verified.')
    else:
        if not all((a.source,a.bridge,a.icarus,a.out)):p.error('Need source, bridge, runtime and output')
        run(a.source,a.bridge,a.icarus,a.out)
