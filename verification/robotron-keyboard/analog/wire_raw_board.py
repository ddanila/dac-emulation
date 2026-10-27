#!/usr/bin/env python3
"""Bind and budget all allocated board wire filters before execution."""
import argparse,json,math,os,platform,re,shutil,subprocess
from pathlib import Path
import net_budget as graph
from net_probe import parse as graph_parse
from net_types_probe import parse,bind
from wire_probe import parse as parse_wires
from wire_raw_probe import parse as parse_raw,triplet
from wire_board import bind_wires
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


def bind_raw(nodes,types,wires,raw):
    bind_wires(nodes,types,wires)
    if raw['tick']!=nodes['tick']:raise ValueError('Raw wire/graph time mismatch')
    expected=[w for w in wires['filters'] if w['kind']==8]
    if len(expected)!=len(raw['filters']):raise ValueError('Missing raw board wire filter')
    for old,new in zip(expected,raw['filters']):
        if any(old[k]!=new[k] for k in ('id','node','pointer')):
            raise ValueError('Raw wire binding differs from graph/class')
        for name,value in zip(('driven','forced'),new['vectors']):
            prior=old['vectors'][name]
            if prior['bits']!=(''.join(map(triplet,value)) if value else '-'):
                raise ValueError('Raw/legacy wire payload mismatch')
    return len(expected)


def review(root):
    result=graph.review(root)
    before=(root/'types-before.txt').read_text()
    if before!=(root/'types-after.txt').read_text():raise ValueError('Class observation changed state')
    types=parse(before.splitlines());nodes=graph_parse((root/'before.txt').read_text().splitlines())
    classes=bind(nodes,types)
    raw=(root/'wires-before.txt').read_text()
    if raw!=(root/'wires-after.txt').read_text():raise ValueError('Wire observation changed state')
    wires=parse_wires(raw.splitlines())
    raw=(root/'raw-before.txt').read_text()
    if raw!=(root/'raw-after.txt').read_text():raise ValueError('Raw wire observation changed state')
    exact=parse_raw(raw.splitlines());count=bind_raw(nodes,types,wires,exact)
    result.update(nativeClassBindingsMatchGraph=True,nativeClasses=classes,rawWireFilters=count,rawBytesPreserved=True,legacyViewsAgree=True)
    calls=result['projection']['normalSnapshotCalls']
    # The shared benchmark validator checks measurements; this fixture times wires.
    result['rawWireTimings']=result.pop('timings')
    result['rawWireImageBytes']=len(raw.encode())
    old=result['projection']
    result['projection']=dict(boundaries=old['boundaries'],normalSnapshotCalls=calls,
        rawWireLogBytesAtInitialState=calls*result['rawWireImageBytes'],
        meanRawWireScanSeconds=old['meanScanSeconds'],maxSampleRawWireScanSeconds=old['maxSampleScanSeconds'],
        excludesTimeDigitGrowthLaterStateAndOtherObservers=True)
    result['scope']='Actual compiled board before execution: every allocated vec8 filter bound to graph, native class and legacy view, with repeatable exact driven/forced cache bytes. Timings measure raw vec8 scans/serialization only. Initial-state output projection is not an operational upper bound.'
    result['notEstablished']=['Raw strength state in other payload families','Compact encoding, operational raw-wire state and combined capture/review budget','Functor payloads, full coupled qualification or general rollback']
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
    shutil.copy2(HERE/'fixtures/wire_raw_board.c',out/'probe.c')
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
        sources={n:sha(HERE/n) for n in ('wire_raw_board.py','wire_board.py','wire_raw_probe.py','strength_encoding_probe.py','wire_probe.py','island_filter_probe.py','net_budget.py','net_types_probe.py','net_probe.py','net_source_contract.py','array_probe.py','array_source_contract.py','code_operand_board_review.py','code_operand_probe.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/wire_raw_board.c')}),indent=2)+'\n')
    result.check_returncode()
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('source','candidate','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed budget assessment')
        print('Complete board raw-wire bindings verified with measured budget.')
    else:
        if not all((a.source,a.candidate,a.out)):p.error('Need source, candidate and output')
        run(a.source,a.candidate,a.out)
