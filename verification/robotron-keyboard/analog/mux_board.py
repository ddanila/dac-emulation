#!/usr/bin/env python3
"""Bind and budget every MUXZ on the compiled board."""
import argparse,collections,json,math,os,platform,re,shutil,subprocess
from pathlib import Path
import net_budget as graph
from net_probe import parse as graph_parse
from net_types_probe import parse,bind
from mux_probe import parse as parse_muxes
from mux_probe import validate as validate_muxes
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


def bind_muxes(graph,types,muxes,compiled):
    bind(graph,types);validate_muxes(muxes)
    if graph['tick']!=muxes['tick']:raise ValueError('Mux/graph time mismatch')
    native=[n for n in types['nodes'] if (n['funClass'] or '').startswith('vvp_fun_mux')]
    if len(native)!=len(muxes['muxes']):raise ValueError('Missing allocated mux functor')
    for n,m in zip(native,muxes['muxes']):
        if (n['id'],n['key'],n['fun'],n['funClass'])!=(m['id'],m['node'],m['fun'],'vvp_fun_muxz'):raise ValueError('Wrong mux class/graph binding')
        if m['aWidth']!=m['bWidth']:raise ValueError('Unequal mux input widths')
    widths=[]
    for line in compiled.splitlines():
        if '.functor MUX' not in line:continue
        match=re.fullmatch(r'\S+ \.functor MUXZ ([1-9][0-9]*), .+;',line)
        if not match:raise ValueError('Unsupported compiled mux family')
        widths.append(int(match[1]))
    if not widths or collections.Counter(widths)!=collections.Counter(m['aWidth'] for m in muxes['muxes']):raise ValueError('Compiled mux widths differ from native caches')
    return len(native)


def review(root):
    result=graph.review(root)
    before=(root/'types-before.txt').read_text()
    if before!=(root/'types-after.txt').read_text():raise ValueError('Class observation changed state')
    types=parse(before.splitlines());nodes=graph_parse((root/'before.txt').read_text().splitlines())
    classes=bind(nodes,types)
    raw=(root/'muxes-before.txt').read_text()
    if raw!=(root/'muxes-after.txt').read_text():raise ValueError('Mux observation changed state')
    muxes=parse_muxes(raw.splitlines());count=bind_muxes(nodes,types,muxes,(root/'board.vvp').read_text())
    result.update(nativeClassBindingsMatchGraph=True,nativeClasses=classes,muxFunctors=count)
    calls=result['projection']['normalSnapshotCalls']
    result['muxTimings']=result.pop('timings');result['muxImageBytes']=len(raw.encode())
    old=result['projection']
    result['projection']=dict(boundaries=old['boundaries'],normalSnapshotCalls=calls,muxLogBytesAtInitialState=calls*(result['muxImageBytes']+old['fullGraphLogBytes']//calls-result['logicalImageBytes']),
        meanMuxScanSeconds=old['meanScanSeconds'],maxSampleMuxScanSeconds=old['maxSampleScanSeconds'],excludesLaterStateGrowthAndOtherObservers=True)
    result['scope']='Actual compiled board before time advances: all allocated MUXZ functors bound to graph and native class; pending destinations and wrapper ownership checked. Compiled width totals are an independent aggregate check, not named-net identity. Timings include full cache and scheduler-wrapper scans; initial-state output is not an operational bound.'
    result['notEstablished']=['Operational mux transitions and scheduler growth','Combined capture/review cost and full-board integration','Other payload families, full coupled qualification or general rollback']
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
    shutil.copy2(HERE/'fixtures/mux_board.c',out/'probe.c')
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
        sources={n:sha(HERE/n) for n in ('mux_board.py','mux_probe.py','net_budget.py','net_types_probe.py','net_probe.py','net_source_contract.py','array_probe.py','array_source_contract.py','code_operand_board_review.py','code_operand_probe.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/mux_board.c')}),indent=2)+'\n')
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
