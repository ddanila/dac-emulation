#!/usr/bin/env python3
"""Bounded keyboard retained-waveform transport benchmark; never resumes full-repeat qualification."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import threading
import time
from retained_stream_refinement import capture
from retained_stream_review import replay
from keyboard_stream_benchmark import check as check_baseline
from ttl7406_probe import sha


def descendants(rows, root):
    selected={root}
    while True:
        expanded=selected|{pid for pid,parent,rss in rows if parent in selected}
        if expanded==selected:return [(pid,rss) for pid,parent,rss in rows if pid in selected]
        selected=expanded


def run(source, runtime, spinit, out):
    runner_digest=sha(Path(__file__))
    source=source.resolve();out=out.resolve()
    check_baseline(source)
    prior=source
    receipt=json.loads((prior/'capture/assessment.json').read_text())
    source=prior/'inputs-0'
    if sha(source/'io.cir')!=receipt['sourceDecks'][0]['sha256']:raise ValueError('Changed baseline deck')
    for name,digest in receipt['inputs'].items():
        if sha(source/name)!=digest:raise ValueError('Changed observer fixture input')
    original=(source/'io.cir').read_text()
    if len(re.findall(r'^\.tran 25n 20000n$',original,re.M))!=1:
        raise ValueError('Expected retained 20-us observer fixture')
    saves=re.findall(r'^\.save (.+)$',original,re.M)
    if len(saves)!=1:raise ValueError('Expected one observation list')
    # Repeated save requests identify the same node, not extra observations.
    text=original.replace('.save '+saves[0],'.save '+' '.join(dict.fromkeys(saves[0].split())))
    out.mkdir(parents=True,exist_ok=False)
    decks=[]
    for index,step in enumerate(('25','12.5','6.25')):
        folder=out/f'inputs-{index}';folder.mkdir()
        for name in ('io.vvp','s600.hex'):shutil.copyfile(source/name,folder/name)
        deck=folder/'io.cir';deck.write_text(text.replace('.tran 25n 20000n',f'.tran {step}n 20000n'));decks.append(deck)
    samples=[];errors=[];stop=threading.Event();start=time.monotonic()
    def monitor():
        try:
            while not stop.is_set():
                listing=subprocess.check_output(['ps','-axo','pid=,ppid=,rss='],text=True)
                rows=[tuple(map(int,line.split())) for line in listing.splitlines()]
                processes=descendants(rows,os.getpid())
                samples.append({'seconds':time.monotonic()-start,'rssKiB':sum(rss for pid,rss in processes),'processes':len(processes)})
                stop.wait(.5)
        except Exception as exc:errors.append(str(exc))
    thread=threading.Thread(target=monitor);thread.start()
    try:
        result=capture(decks,out/'capture',runtime,spinit,900,['io.vvp','s600.hex'],receipt['environment'],
                       storage_limits=dict(max_raw_bytes=256*1024**2,max_compressed_raw_bytes=128*1024**2,
                           max_log_bytes=128*1024**2,max_compressed_log_bytes=64*1024**2,max_log_line_bytes=1024**2))
    finally:
        stop.set();thread.join()
        (out/'resource-samples.json').write_text(json.dumps({'samples':samples,'errors':errors},indent=2)+'\n')
    if errors or not samples:raise ValueError('Resource sampling failed')
    reviewed=replay(out/'capture')
    if reviewed['comparisons']!=receipt['transport']['comparisons']:raise ValueError('Changed baseline comparisons')
    logs=list((out/'capture').glob('*.log.xz'))
    result={'sourceReceiptSha256':sha(prior/'capture/assessment.json'),'benchmarkSha256':runner_digest,
            'elapsedSeconds':time.monotonic()-start,'sampledMaximumTreeRssKiB':max(s['rssKiB'] for s in samples),
            'memoryScope':'Sampled benchmark process and descendants, including ps; not an exact peak or a full-repeat bound.',
            'compressedLogBytes':sum(p.stat().st_size for p in logs),
            'rawBytesCompared':sum(s['bytes'] for s in result['transport']['streams']),
            'retainedReplayPassed':True,'baselineComparisonsExactlyEqual':True,
            'storageLimits':result['transport']['storageLimits'],'storageUsage':reviewed['storageUsage'],
            'voltageGatePassed':result['voltageGatePassed'],'qualified':False,
            'scope':'Lossless retention revision of the complete 20-us observer fixture at three timestep levels; duplicate save requests removed without removing distinct signals. No full-repeat or serial-scenario acceptance.'}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


def check(root):
    manifest=json.loads((root/'manifest.json').read_text())
    actual={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p.name!='manifest.json'}
    if actual!=manifest['files']:raise ValueError('Changed benchmark evidence')
    for name,digest in manifest['sources'].items():
        if sha(Path(__file__).parent/name)!=digest:raise ValueError('Changed benchmark source: '+name)
    replay(root/'capture')
    if json.loads((root/'assessment.json').read_text())['qualified'] is not False:
        raise ValueError('Bounded benchmark cannot qualify the board')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','runtime','spinit','out'):p.add_argument('--'+name,type=Path)
    p.add_argument('--check',type=Path);a=p.parse_args()
    if a.check:check(a.check)
    else:
        if not all((a.source,a.runtime,a.spinit,a.out)):p.error('Need source, runtime, spinit and out')
        run(a.source,a.runtime,a.spinit,a.out)
