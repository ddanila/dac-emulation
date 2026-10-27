#!/usr/bin/env python3
"""Measure complete board mux deltas without skipping native field scans."""
import argparse,json,math,os,platform,re,shutil,subprocess
from pathlib import Path
import net_budget as graph
from net_probe import parse as graph_parse
from net_types_probe import parse,bind
from mux_probe import parse as parse_muxes
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


def review(root):
    from mux_board import review as full_review
    from mux_delta_probe import block,reconstruct
    result=full_review(root)
    lines=(root/'mux-reference.txt').read_text().splitlines()
    reference,end=block(lines)
    if end!=len(lines) or reference['mode']!='R':raise ValueError('Invalid mux reference')
    for suffix in ('before','after'):
        lines=(root/('mux-delta-'+suffix+'.txt')).read_text().splitlines()
        delta,end=block(lines)
        if end!=len(lines) or delta['rows'] or delta['events']:raise ValueError('Changed unchanged-board delta')
        actual=reconstruct(reference['rows'],delta)
        full=(root/('muxes-'+suffix+'.txt')).read_text().splitlines()
        if actual!=full:raise ValueError('Board mux delta differs from dense image')
    calls=result['projection']['normalSnapshotCalls']
    result['muxDeltaTimings']=result.pop('muxTimings')
    size=(root/'mux-delta-before.txt').stat().st_size
    refsize=(root/'mux-reference.txt').stat().st_size
    result.update(denseAndDeltaExactlyEqual=True,muxDeltaBytes=size,muxReferenceBytes=refsize)
    result['projection'].update(muxDeltaLogBytesAtInitialState=calls*(size+result['projection']['muxLogBytesAtInitialState']//calls-result['muxImageBytes'])+refsize)
    result['scope']='Actual compiled board before execution: unchanged full-scan mux deltas reconstruct exact complete payload images bound to graph/classes. Timings measure full scan plus delta encoding. Output estimates assume unchanged state and exclude operational changes and other observers.'
    return result


def run(source,candidate,out):
    source=source.resolve();candidate=candidate.resolve();out=out.resolve();check(source);out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed runtime')
    shutil.copy2(candidate/'build.json',out/'build.json')
    original=source/'off/io.vvp';receipt=json.loads((source/'off/run.json').read_text())
    assessment=json.loads((source/'assessment.json').read_text())
    if not assessment['controlsPassed'] or assessment['receipts']['off']!=sha(source/'off/run.json'):raise ValueError('Need reviewed board')
    module=next(d['path'] for d in receipt['externalDependencies'] if Path(d['path']).name=='system.vpi')
    old=':vpi_module "'+module+'";';vvp=original.read_text()
    if vvp.count(old)!=1:raise ValueError('Unexpected module placement')
    (out/'board.vvp').write_text(vvp.replace(old,':vpi_module "'+str(candidate/'vpi/system.vpi')+'";'))
    shutil.copy2(HERE/'fixtures/mux_delta_board.c',out/'probe.c')
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    command=['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')]
    subprocess.run(command,check=True)
    modules=[Path(n) for n in re.findall(r'^:vpi_module "([^"]+)";$',(out/'board.vvp').read_text(),re.M)]
    pins={str(p):sha(p) for p in [candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',out/'board.vvp',*modules]}
    env=dict(os.environ);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(candidate/'vvp')
    cmd=[str(candidate/'vvp/vvp'),'-M.','-mprobe','board.vvp']
    result=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=120)
    (out/'stdout.txt').write_text(result.stdout);(out/'stderr.txt').write_text(result.stderr)
    if any(sha(Path(p))!=digest for p,digest in pins.items()):raise ValueError('Changed runtime during probe')
    (out/'run.json').write_text(json.dumps(dict(exitCode=result.returncode,compileCommand=command,command=cmd,dependencies=pins,
        originalCompiledSha256=sha(original),baselineReceiptSha256=sha(source/'off/run.json'),assessmentSha256=sha(source/'assessment.json'),
        reviewedBoundaries=assessment['observedState']['boundaries'],endSeconds=receipt['endSeconds'],
        priorObserverProducerSeconds=json.loads((source/'observe/run.json').read_text())['log']['elapsedSeconds'],
        sourceManifestSha256=sha(source/'manifest.json'),rssUnitBytes=1 if platform.system()=='Darwin' else 1024,platform=platform.platform(),
        sources={n:sha(HERE/n) for n in ('mux_delta_board.py','mux_board.py','mux_delta_probe.py','mux_probe.py','net_budget.py','net_types_probe.py','net_probe.py','net_source_contract.py','array_probe.py','array_source_contract.py','code_operand_board_review.py','code_operand_probe.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/mux_delta_board.c')}),indent=2)+'\n')
    result.check_returncode()
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('source','candidate','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed budget assessment')
        print('Complete board mux bindings verified with measured budget.')
    else:
        if not all((a.source,a.candidate,a.out)):p.error('Need source, candidate and output')
        run(a.source,a.candidate,a.out)
