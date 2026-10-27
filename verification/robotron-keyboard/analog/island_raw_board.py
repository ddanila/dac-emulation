#!/usr/bin/env python3
"""Bind compiled-board raw islands to native graph/classes and measure full scans."""
import argparse,collections,json,os,platform,re,shutil,subprocess
from pathlib import Path
import net_budget as graph
from net_probe import parse as graph_parse
from net_types_probe import parse as parse_types,bind as bind_types
from island_raw_probe import parse as parse_raw,bind as bind_raw
from island_probe import parse_snapshot,validate_normal
from island_raw_contract import profile
from island_raw_delta import block,reconstruct
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent

def bind_islands(nodes,types,raw,legacy,compiled):
    classes=bind_types(nodes,types);bind_raw(raw,legacy);validate_normal(legacy)
    if nodes['tick']!=raw['tick']:raise ValueError('Island/graph time mismatch')
    native={n['key']:n for n in types['nodes'] if n['funClass']=='vvp_island_port'};seen=set();signatures=[]
    for island in legacy['islands']:
        ports={p['id']:p for p in island['ports']};indices={p['net']:p['id'] for p in ports.values()}
        for p in ports.values():
            n=native.get(p['net'])
            if not n or (p['functor'],p['filter'])!=(n['fun'],n['filter']) or p['net'] in seen:raise ValueError('Missing/aliased island port graph or class binding')
            seen.add(p['net'])
        branches=[]
        for b in island['branches']:
            if (b['width'],b['part'],b['offset'],b['resistive'])!=(0,0,0,0) or b['enable'] not in indices:raise ValueError('Unadmitted board switch family')
            branches.append((b['a'],b['b'],indices[b['enable']],b['active']))
        signatures.append((len(ports),tuple(branches)))
    if seen!=set(native):raise ValueError('Unobserved native island port')
    compiled_profile=profile(compiled);expected=[]
    for label in compiled_profile['islands']:
        ports=[p for p in compiled_profile['ports'] if p['island']==label];indices={p['label']:i+1 for i,p in enumerate(ports)}
        branches=[(indices[b['a']],indices[b['b']],indices[b['enable']],int(b['kind']=='tranif1')) for b in compiled_profile['branches'] if b['island']==label]
        expected.append((len(ports),tuple(branches)))
    if collections.Counter(expected)!=collections.Counter(signatures):raise ValueError('Compiled island membership or branch routing differs from native mesh')
    return dict(islands=len(signatures),ports=len(seen),branches=sum(len(s[1]) for s in signatures),nativeClasses=classes,bindingLimit='Native port pointers bind exactly to graph/classes. Compiled port-order/branch signatures are an independent structural multiset check, not named-net correspondence.')

def review(root):
    result=graph.review(root)
    def stable(name):
        text=(root/(name+'-before.txt')).read_text()
        if text!=(root/(name+'-after.txt')).read_text():raise ValueError('Observer changed '+name)
        return text
    types=parse_types(stable('types').splitlines());nodes=graph_parse((root/'before.txt').read_text().splitlines())
    raw_text=stable('island_raw');raw=parse_raw(raw_text.splitlines());legacy=parse_snapshot(stable('island-legacy').splitlines())
    bindings=bind_islands(nodes,types,raw,legacy,(root/'board.vvp').read_text())
    lines=(root/'island_raw-reference.txt').read_text().splitlines();reference,end=block(lines)
    if end!=len(lines) or reference['mode']!='R':raise ValueError('Invalid island reference')
    for suffix in ('before','after'):
        lines=(root/('island_raw-delta-'+suffix+'.txt')).read_text().splitlines();delta,end=block(lines)
        if end!=len(lines) or delta['rows'] or reconstruct(reference['rows'],delta)!=raw_text.splitlines():raise ValueError('Board compact island image differs from full image')
    old=result['projection'];calls=old['normalSnapshotCalls'];digits=old['fullGraphLogBytes']//calls-result['logicalImageBytes']
    size=(root/'island_raw-delta-before.txt').stat().st_size;refsize=(root/'island_raw-reference.txt').stat().st_size
    result.update(pendingIslands=sum(n['flag'] for n in legacy['islands']),islandBindings=bindings,rawIslandImageBytes=len(raw_text.encode()),rawIslandDeltaBytes=size,rawIslandReferenceBytes=refsize,denseAndDeltaExactlyEqual=True,observedVectorWidths=dict(sorted(collections.Counter(str(len(v)) for n in raw['islands'] for p in n['ports'] for v in p['vectors'].values()).items())))
    result['rawIslandDeltaTimings']=result.pop('timings')
    result['projection']=dict(boundaries=old['boundaries'],normalSnapshotCalls=calls,rawIslandDenseLogBytesAtInitialState=calls*(len(raw_text.encode())+digits),rawIslandDeltaLogBytesAtInitialState=calls*(size+digits)+refsize,meanRawIslandScanSeconds=old['meanScanSeconds'],maxSampleRawIslandScanSeconds=old['maxSampleScanSeconds'],excludesLaterStateGrowthAndOtherObservers=True)
    result['scope']='Actual compiled keyboard board before time advances: complete raw island vectors bind to legacy mesh topology, every native port class and allocated graph/filter identity. Compact images reconstruct dense state exactly. Timings include full raw scans and difference encoding; projections assume unchanged initial state.'
    result['notEstablished']=['Operational board transitions, growth and combined cost','Named compiled-net correspondence and other reachable payloads','General rollback or full coupled qualification']
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
    shutil.copy2(HERE/'fixtures/island_raw_board.c',out/'probe.c')
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
        sources={n:sha(HERE/n) for n in ('island_raw_board.py','island_raw_delta.py','island_raw_probe.py','island_probe.py','island_raw_contract.py','wire_raw_probe.py','net_budget.py','net_types_probe.py','net_probe.py','net_source_contract.py','array_probe.py','array_source_contract.py','code_operand_board_review.py','code_operand_probe.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/island_raw_board.c')}),indent=2)+'\n')
    result.check_returncode()
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('source','candidate','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed budget assessment')
        print('Raw island board bindings and initial scan budget verified.')
    else:
        if not all((a.source,a.candidate,a.out)):p.error('Need source, candidate and output')
        run(a.source,a.candidate,a.out)
