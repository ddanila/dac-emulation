#!/usr/bin/env python3
"""Measure complete static board array observation before HDL execution."""
import argparse,collections,json,math,os,platform,re,shutil,subprocess
from pathlib import Path
from array_probe import parse,validate
from array_source_contract import profile
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


def review(root):
    receipt=json.loads((root/'run.json').read_text())
    if receipt['exitCode']!=0 or (root/'stderr.txt').read_text():raise ValueError('Failed array cost probe')
    before=(root/'before.txt').read_text();after=(root/'after.txt').read_text()
    if before!=after:raise ValueError('Array observation changed state')
    snapshot=parse(before.splitlines());validate(snapshot)
    if snapshot['tick']!=0:raise ValueError('HDL execution occurred')
    compiled=profile((root/'board.vvp').read_text())
    counts=collections.Counter(p['array'] for p in compiled['ports'])
    expected=collections.Counter((a['words'],a['width'],a['msb'],a['lsb'],counts[a['label']]) for a in compiled['arrays'])
    actual=collections.Counter((a['size'],a['width'],a['msb'],a['lsb'],sum(p['array']==a['id'] for p in snapshot['ports'])) for a in snapshot['arrays'])
    if actual!=expected:raise ValueError('Native arrays/ports differ from compiled board')
    if any(a['cache'] or any(set(w)!={'3'} for w in a['words']) for a in snapshot['arrays']):raise ValueError('Expected uninitialized memory before HDL execution')
    lines=(root/'stdout.txt').read_text().splitlines()
    if len(lines)!=3 or lines[-1]!='ARRAY_BUDGET_DONE':raise ValueError('Unexpected benchmark output or HDL execution')
    a=lines[0].split();r=lines[1].split()
    if len(a)!=5 or a[:2]!=['ARRAY_BUDGET','64'] or len(r)!=2 or r[0]!='ARRAY_RSS':raise ValueError('Invalid budget markers')
    total,minimum,maximum=map(float,a[2:]);rss=int(r[1])*receipt['rssUnitBytes']
    if not all(math.isfinite(x) for x in (total,minimum,maximum)) or not 0<minimum<=total/64<=maximum or rss<=0:raise ValueError('Invalid budget measurements')
    boundaries=receipt['reviewedBoundaries']
    if not isinstance(boundaries,int) or boundaries<=0:raise ValueError('Invalid boundary count')
    calls=boundaries*2;size=len(before.encode())
    precision=re.findall(r'^:vpi_time_precision (-?\s*\d+);$',(root/'board.vvp').read_text(),re.M)
    if len(precision)!=1:raise ValueError('Missing time precision')
    ticks=math.ceil(receipt['endSeconds']/10**int(precision[0].replace(' ','')))
    digits=max(0,len(str(ticks))-1)
    # Cache allocation after firmware initialization adds a row per word and
    # per array. This pre-execution image must not be treated as a log cap.
    return dict(qualified=False,compiledBoardArrayImageComplete=True,observationExactlyRepeatable=True,
        arrays=len(snapshot['arrays']),readPorts=len(snapshot['ports']),logicalBits=sum(a['size']*a['width'] for a in snapshot['arrays']),
        timings=dict(iterations=64,totalSeconds=total,meanSeconds=total/64,minSeconds=minimum,maxSeconds=maximum),
        peakResidentBytes=rss,logicalImageBytes=size,
        projection=dict(boundaries=boundaries,normalSnapshotCalls=calls,uncachedImageLogBytes=calls*(size+digits),
            meanScanSeconds=calls*total/64,maxSampleScanSeconds=calls*maximum,
            excludesLaterWordHandleAllocation=True,excludesOtherObserversAndCompression=True),
        scope='Complete compiled board array/read-port inventory before firmware execution. Unwritten X words and absent word handles remain unchanged. Host measurements are not runtime guarantees.',
        notEstablished=['Loaded ROM/register and read-address behavior at operational boundaries','Combined campaign runtime, compression and review cost','Later word-handle cache growth; projection is not a capture cap','General rollback or destination net/fanout contents'])


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
    shutil.copy2(HERE/'fixtures/array_budget.c',out/'probe.c')
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
        sources={n:sha(HERE/n) for n in ('array_budget.py','array_probe.py','array_source_contract.py','compiled_scope_profile.py','thread_board_reachability.py','fixtures/array_budget.c')}),indent=2)+'\n')
    result.check_returncode()
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('source','candidate','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed budget assessment')
        print('Complete board array image and measured budget verified.')
    else:
        if not all((a.source,a.candidate,a.out)):p.error('Need source, candidate and output')
        run(a.source,a.candidate,a.out)
