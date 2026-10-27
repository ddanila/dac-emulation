#!/usr/bin/env python3
"""Bind raw board assignments to ordered queues, legacy payloads and graph targets."""
import argparse,collections,json,os,platform,re,shutil,subprocess
from pathlib import Path
import net_budget as graph
from net_probe import parse as graph_parse
from net_types_probe import parse as parse_types,bind as bind_types,class_name
from assignment_raw import parse as parse_raw,bind as bind_raw
from assignment_probe import parse_snapshot
from private_queue_probe import snapshot as parse_queue
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


def bind_assignments(nodes,types,raw,legacy,queue_lines):
    bind_types(nodes,types);bind_raw(raw,legacy);queue=parse_queue(queue_lines)
    if nodes['tick']!=raw['tick'] or queue['time']!=raw['tick']:raise ValueError('Assignment/graph/queue time mismatch')
    native={n['key']:n for n in types['nodes']};expected=set();seen=set();classes=collections.Counter()
    for line in queue_lines:
        a=line.split()
        if a[0]=='VQ_EVENT' and class_name(a[4])=='assign_vector8_event_s':expected.add((int(a[1]),a[2],int(a[3])))
    for e in raw['events']:
        target=native.get(int(e['target'],16))
        if target is None or not target['fun']:raise ValueError('Assignment destination is not an allocated receiving node')
        classes[target['funClass']]+=1
        if e['region']!='executing':seen.add((e['slot'],e['region'],e['ordinal']))
    if seen!=expected:raise ValueError('Raw payloads do not cover exact native assignment queue positions')
    return dict(pendingAssignments=len(seen),executingAssignments=sum(e['region']=='executing' for e in raw['events']),targetClasses=dict(sorted(classes.items())),uniqueTargets=len({e['target'] for e in raw['events']}),rawPayloadBytes=sum(len(e['raw']) for e in raw['events']),bindingLimit='Exact queue positions/classes, legacy lifetime/port/payload identities and allocated native destination nodes. No named compiled-net correspondence or claim that initial populations bound operational state.')


def review(root):
    result=graph.review(root)
    def stable(name):
        text=(root/(name+'-before.txt')).read_text()
        if text!=(root/(name+'-after.txt')).read_text():raise ValueError('Observer changed '+name)
        return text
    nodes=graph_parse((root/'before.txt').read_text().splitlines());types=parse_types(stable('types').splitlines())
    raw_text=stable('assignment_raw');raw=parse_raw(raw_text.splitlines());legacy=parse_snapshot(stable('assignment-legacy').splitlines());queue=stable('queue').splitlines()
    bindings=bind_assignments(nodes,types,raw,legacy,queue)
    if bindings['executingAssignments']:raise ValueError('Unexpected assignment executing at startup callback')
    old=result['projection'];calls=old['normalSnapshotCalls'];digits=old['fullGraphLogBytes']//calls-result['logicalImageBytes']
    result.update(assignmentBindings=bindings,rawAssignmentImageBytes=len(raw_text.encode()),observedVectorWidths=dict(sorted(collections.Counter(str(len(e['raw'])) for e in raw['events']).items())))
    result['rawAssignmentTimings']=result.pop('timings')
    result['projection']=dict(boundaries=old['boundaries'],normalSnapshotCalls=calls,rawAssignmentLogBytesAtInitialState=calls*(len(raw_text.encode())+digits),meanRawAssignmentScanSeconds=old['meanScanSeconds'],maxSampleRawAssignmentScanSeconds=old['maxSampleScanSeconds'],excludesLaterStateGrowthAndOtherObservers=True)
    result['scope']='Compiled keyboard board at startup before time advances. Complete raw strength assignments bind to ordered native queue classes, legacy values/lifetimes/ports and allocated graph targets. Full native scans are timed; projections assume unchanged initial state.'
    result['notEstablished']=['Operational transitions, executing assignment bindings and growth','Combined capture/review cost and named compiled-net correspondence','General rollback or full coupled qualification']
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
    shutil.copy2(HERE/'fixtures/assignment_raw_board.c',out/'probe.c')
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
        sources={n:sha(HERE/n) for n in ('assignment_raw_board.py','assignment_raw.py','assignment_probe.py','private_queue_probe.py','wire_raw_probe.py','net_budget.py','net_types_probe.py','net_probe.py','net_source_contract.py','array_probe.py','array_source_contract.py','code_operand_board_review.py','code_operand_probe.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/assignment_raw_board.c')}),indent=2)+'\n')
    result.check_returncode()
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('source','candidate','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed budget assessment')
        print('Raw assignment board bindings and initial scan budget verified.')
    else:
        if not all((a.source,a.candidate,a.out)):p.error('Need source, candidate and output')
        run(a.source,a.candidate,a.out)
