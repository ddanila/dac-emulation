#!/usr/bin/env python3
"""Bind and budget every concat on the compiled board."""
import argparse,collections,json,math,os,platform,re,shutil,subprocess
from pathlib import Path
import net_budget as graph
from net_probe import parse as graph_parse
from net_types_probe import parse,bind
from concat_probe import parse as parse_concat
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


KINDS={'vvp_fun_concat':4,'vvp_fun_concat8':8}


def bind_concat(graph,types,state,compiled):
    bind(graph,types)
    if graph['tick']!=state['tick']:raise ValueError('Concat/graph time mismatch')
    native=[n for n in types['nodes'] if n['funClass'] in KINDS]
    if len(native)!=len(state['nodes']):raise ValueError('Missing allocated concat functor')
    actual=[];keys={}
    for n,g in zip(native,state['nodes']):
        if (n['id'],n['key'],n['fun'],KINDS[n['funClass']])!=(g['id'],g['node'],g['fun'],g['kind']):raise ValueError('Wrong concat class/graph binding')
        if g['width']!=sum(g['widths']):raise ValueError('Concat width does not cover all ports')
        if g['pending'] not in (0,g['node']):raise ValueError('Foreign pending output node')
        if g['event'] in keys:raise ValueError('Aliased concat event key')
        keys[g['event']]=g;actual.append((g['kind'],tuple(g['widths'])))
    events={}
    for e in state['events']:
        if e['key'] not in keys or e['key'] in events or e['delete']!=0 or e['id']<=0:raise ValueError('Wrong concat wrapper binding')
        if e['region']=='executing':
            if e['slot']!=-2 or keys[e['key']]['pending']:raise ValueError('Wrong executing concat binding')
        elif not keys[e['key']]['pending']:raise ValueError('Queued concat without pending node')
        events[e['key']]=e
    if any(g['pending'] and g['event'] not in events for g in state['nodes']):raise ValueError('Pending concat without queued wrapper')
    expected=[]
    for line in compiled.splitlines():
        if not re.match(r'\S+ \.concat',line):continue
        m=re.fullmatch(r'\S+ \.(concat8?) \[\s*(\d+) (\d+) (\d+) (\d+)\], (.+);',line)
        if not m:raise ValueError('Unadmitted compiled concatenation')
        widths=tuple(map(int,m.group(2,3,4,5)))
        expected.append((8 if m[1]=='concat8' else 4,widths))
    if not expected or collections.Counter(expected)!=collections.Counter(actual):raise ValueError('Compiled concat families/port widths differ from native caches')
    return len(native)


def review(root):
    result=graph.review(root)
    before=(root/'types-before.txt').read_text()
    if before!=(root/'types-after.txt').read_text():raise ValueError('Class observation changed state')
    types=parse(before.splitlines());nodes=graph_parse((root/'before.txt').read_text().splitlines())
    classes=bind(nodes,types)
    raw=(root/'concat-before.txt').read_text()
    if raw!=(root/'concat-after.txt').read_text():raise ValueError('Concat observation changed state')
    concats=parse_concat(raw.splitlines());count=bind_concat(nodes,types,concats,(root/'board.vvp').read_text())
    result.update(nativeClassBindingsMatchGraph=True,nativeClasses=classes,concatFunctors=count,observedCacheWidths={str(k):v for k,v in sorted(collections.Counter(n['width'] for n in concats['nodes']).items())})
    calls=result['projection']['normalSnapshotCalls']
    result['concatTimings']=result.pop('timings');result['concatImageBytes']=len(raw.encode())
    old=result['projection']
    result['projection']=dict(boundaries=old['boundaries'],normalSnapshotCalls=calls,concatLogBytesAtInitialState=calls*(result['concatImageBytes']+old['fullGraphLogBytes']//calls-result['logicalImageBytes']),
        meanConcatScanSeconds=old['meanScanSeconds'],maxSampleConcatScanSeconds=old['maxSampleScanSeconds'],excludesLaterStateGrowthAndOtherObservers=True)
    result['scope']='Actual compiled board before time advances: all admitted allocated concat functors bound to graph and native class; raw concat8 bytes and logical concat4 bits observed with port widths and pending/event bindings. Compiled family/width totals are an independent aggregate check, not named-net identity. Timings include full cache scans; initial-state output is not an operational bound.'
    result['notEstablished']=['Operational concat transitions and allocation growth','Combined capture/review cost and full-board integration','Other payload families, full coupled qualification or general rollback']
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
    shutil.copy2(HERE/'fixtures/concat_board.c',out/'probe.c')
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
        sources={n:sha(HERE/n) for n in ('concat_board.py','concat_probe.py','mux_probe.py','net_budget.py','net_types_probe.py','net_probe.py','net_source_contract.py','array_probe.py','array_source_contract.py','code_operand_board_review.py','code_operand_probe.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/concat_board.c')}),indent=2)+'\n')
    result.check_returncode()
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('source','candidate','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed budget assessment')
        print('Complete board concat bindings verified with measured budget.')
    else:
        if not all((a.source,a.candidate,a.out)):p.error('Need source, candidate and output')
        run(a.source,a.candidate,a.out)
