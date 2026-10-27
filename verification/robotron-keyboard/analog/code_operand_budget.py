#!/usr/bin/env python3
"""Measure full-board operand scan cost without starting a board simulation."""
import argparse, collections, json, lzma, math, os, platform, re, shutil, subprocess
from pathlib import Path
from code_operand_probe import block, reconstruct
from thread_board_reachability import analyze
from ttl7406_probe import sha
from retained_evidence import check
HERE=Path(__file__).resolve().parent


def text(path):
    if path.exists():return path.read_text()
    with lzma.open(str(path)+'.xz','rt') as f:return f.read()


def review(root):
    receipt=json.loads((root/'run.json').read_text())
    if receipt['exitCode']!=0 or (root/'stderr.txt').read_text():raise ValueError('Failed cost probe')
    frames={}
    for name,mode in [('reference','R'),('full','F'),('delta','D')]:
        lines=text(root/(name+'.txt')).splitlines();frame,end=block(lines,0)
        if end!=len(lines) or frame['mode']!=mode or frame['tick']!=0:raise ValueError('Invalid cost-probe image')
        frames[name]=frame
    reference=frames['reference']['rows']
    if frames['full']['rows']!=reference or reconstruct(reference,frames['delta'])!=reference:raise ValueError('Changed code image')
    count=sum(analyze((root/'board.vvp').read_text())['opcodeCounts'].values())+1
    chunks=(count+1022)//1023
    ids=set()
    for chunk in range(chunks):
        ids.update(chunk*1024+i+1 for i in range(min(1023,count-chunk*1023)))
        ids.add((chunk+1)*1024)
    if set(reference)!=ids:raise ValueError('Incomplete allocated board image')
    schema=json.loads((HERE/'reports/code-operand-contract/assessment.json').read_text())['instructions']
    expected=collections.Counter(of_ZOMBIE=1,of_CHUNK_LINK=chunks)
    for opcode,n in analyze((root/'board.vvp').read_text())['opcodeCounts'].items():
        if opcode not in schema:raise ValueError('Unknown compiled operand schema')
        expected[schema[opcode]['handler']]+=n
    if collections.Counter(row['opcode'] for row in reference.values())!=expected:raise ValueError('Native instruction families differ from compiled board')
    fields={v['handler']:{f['field'] for f in v['fields']} for v in schema.values()}
    fields.update(of_ZOMBIE=set(),of_CHUNK_LINK={'cptr'})
    for row in reference.values():
        if set(row['fields'])!=fields[row['opcode']]:raise ValueError('Incomplete typed operand fields')
        for name,value in row['fields'].items():
            if name in ('cptr','cptr2'):
                pointer,target=map(int,value.split('/'))
                if target not in ids and not (row['opcode']=='of_CHUNK_LINK' and pointer==target==0):raise ValueError('Invalid code target')
                if bool(pointer)!=bool(target):raise ValueError('Invalid code identity')
            elif int(value)<0 or (name in ('net','handle','array') and not int(value)):raise ValueError('Invalid operand value')
    timings={};rss=None
    lines=(root/'stdout.txt').read_text().splitlines()
    if not lines or lines[-1]!='OPERAND_BUDGET_DONE':raise ValueError('Incomplete budget probe')
    for line in lines[:-1]:
        a=line.split()
        if a[0]=='OPERAND_BUDGET' and len(a)==6:
            mode=int(a[1]);iterations=int(a[2]);total,minimum,maximum=map(float,a[3:])
            if mode not in (0,1) or mode in timings or iterations!=64 or not all(math.isfinite(x) for x in (total,minimum,maximum)) or not 0<minimum<=total/iterations<=maximum:raise ValueError('Invalid timing sample')
            timings[mode]=dict(iterations=iterations,totalSeconds=total,meanSeconds=total/iterations,minSeconds=minimum,maxSeconds=maximum)
        elif a[0]=='OPERAND_RSS' and len(a)==2 and rss is None:rss=int(a[1])*receipt['rssUnitBytes']
        else:raise ValueError('Unexpected benchmark output or HDL execution')
    if set(timings)!={0,1} or rss is None or rss<=0:raise ValueError('Missing budget measurements')
    boundaries=receipt['reviewedBoundaries'];calls=boundaries*2
    sizes={name:len(text(root/(name+'.txt')).encode()) for name in frames}
    precision=re.findall(r'^:vpi_time_precision (-?\s*\d+);$',(root/'board.vvp').read_text(),re.M)
    if len(precision)!=1:raise ValueError('Missing time precision')
    ticks=math.ceil(receipt['endSeconds']/10**int(precision[0].replace(' ','')))
    extra_digits=max(0,len(str(ticks))-1)
    prior_seconds=receipt['priorObserverProducerSeconds']
    if not math.isfinite(prior_seconds) or prior_seconds<=0:raise ValueError('Invalid prior capture cost')
    combined=calls*timings[1]['maxSeconds']+prior_seconds
    recommended=math.ceil(2*combined/300)*300
    return dict(qualified=False,compiledBoardOperandImageComplete=True,denseAndDeltaExactlyEqual=True,
                allocatedInstructions=len(reference),timings=timings,peakResidentBytes=rss,logicalImageBytes=sizes,
                projection=dict(boundaries=boundaries,normalSnapshotCalls=calls,
                                fullLogBytes=calls*sizes['full'],unchangedCodeDeltaLogBytesUpperEstimate=sizes['reference']+calls*(sizes['delta']+extra_digits),
                                deltaMeanScanSeconds=calls*timings[1]['meanSeconds'],deltaMaxSampleScanSeconds=calls*timings[1]['maxSeconds'],priorObserverProducerSeconds=prior_seconds,
                                estimatedCombinedProducerSeconds=combined,recommendedCaptureTimeoutSeconds=recommended,
                                unchangedCodeAssumption=True,doesNotBoundFutureChangesOrHostContention=True),
                scope='Actual compiled board at start-of-simulation, before firmware execution. Every allocated instruction is scanned; full and fixed-reference images agree. Timings and projections are observations on this host, not runtime guarantees.',
                notEstablished=['Board execution or faults at operational boundaries','Complete campaign runtime, compression and review cost','Referenced object contents or rollback qualification'])


def run(source,candidate,out):
    source=source.resolve();candidate=candidate.resolve();out=out.resolve();check(source);out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for name,digest in build['outputs'].items():
        if sha(candidate/name)!=digest:raise ValueError('Changed runtime')
    original=source/'off/io.vvp';receipt=json.loads((source/'off/run.json').read_text())
    assessment=json.loads((source/'assessment.json').read_text())
    if not assessment['controlsPassed'] or assessment['receipts']['off']!=sha(source/'off/run.json'):raise ValueError('Need reviewed board')
    module=next(d['path'] for d in receipt['externalDependencies'] if Path(d['path']).name=='system.vpi')
    old=':vpi_module "'+module+'";';vvp=original.read_text()
    if vvp.count(old)!=1:raise ValueError('Unexpected module placement')
    (out/'board.vvp').write_text(vvp.replace(old,':vpi_module "'+str(candidate/'vpi/system.vpi')+'";'))
    shutil.copy2(HERE/'fixtures/code_operand_budget.c',out/'probe.c')
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
        sources={n:sha(HERE/n) for n in ('code_operand_budget.py','code_operand_probe.py','thread_board_reachability.py','reports/code-operand-contract/assessment.json','fixtures/code_operand_budget.c')}),indent=2)+'\n')
    result.check_returncode()
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for name in ('source','candidate','out'):p.add_argument('--'+name,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed budget assessment')
        print('Complete board operand image and measured budget verified.')
    else:
        if not all((a.source,a.candidate,a.out)):p.error('Need source, candidate and output')
        run(a.source,a.candidate,a.out)
