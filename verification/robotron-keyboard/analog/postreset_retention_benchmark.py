#!/usr/bin/env python3
"""Measure complete post-reset retained-stream replay; never execute SPICE."""
import argparse
import hashlib
import json
import lzma
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time

from retained_stream_capture import run as transport
from retained_stream_review import replay
from keyboard_stream_benchmark import descendants
from ttl7406_probe import sha

HERE=Path(__file__).resolve().parent
SOURCES=('postreset_retention_benchmark.py','retained_stream_capture.py','retained_stream_review.py',
         'raw_stream_review.py','raw_waveform.py','host_waveform_comparison.py','filter_truncation_log.py',
         'keyboard_stream_benchmark.py')


def worker(source,fd,receipt_hash):
    if sha(source/'run.json')!=receipt_hash:raise ValueError('Changed producer receipt')
    receipt=json.loads((source/'run.json').read_text())
    for name,destination,expected in (
        ('waveform.raw',os.fdopen(fd,'wb'),receipt['storage']['waveform.raw']),
        ('ngspice.log',sys.stdout.buffer,receipt['log'])):
        digest=hashlib.sha256();size=0
        with lzma.open(source/(name+'.xz'),'rb') as stream:
            for data in iter(lambda:stream.read(65536),b''):
                digest.update(data);size+=len(data);destination.write(data)
        destination.flush()
        if name=='waveform.raw':destination.close()
        if size!=expected['bytes'] or digest.hexdigest()!=expected['sha256']:
            raise ValueError('Changed logical source '+name)


def run(out):
    pinned={n:sha(HERE/n) for n in SOURCES}
    reference=HERE/'reports/postreset-tick'
    prior=json.loads((reference/'assessment.json').read_text())
    retention=json.loads((reference/'retention.json').read_text())
    core=HERE.parents[2]
    sources=[];receipts={};identities={}
    for name,step in (('coarse',25),('fine',12.5),('finest',6.25)):
        source=core/retention['captures'][name]['directory']
        receipt_hash=sha(source/'run.json');r=json.loads((source/'run.json').read_text())
        if receipt_hash!=prior['receipts'][name] or not r['completed'] or r.get('error') or r['exitCode']!=0 or r['stepNs']!=step or r['endSeconds']!=.00116:
            raise ValueError('Invalid complete refinement source')
        for file,expected in retention['captures'][name]['outputs'].items():
            p=source/file
            if p.stat().st_size!=expected['bytes'] or sha(p)!=expected['sha256']:raise ValueError('Changed archived output')
        sources.append(source);receipts[name]=receipt_hash
        identities[name]={'directory':str(source),'outputs':retention['captures'][name]['outputs']}
    out=out.resolve()
    if shutil.disk_usage(out.parent).free<4*1024**3:raise ValueError('Need 4 GiB free before retention replay')
    out.mkdir(exist_ok=False)
    for name,source in zip(receipts,sources):shutil.copy2(source/'run.json',out/(name+'-run.json'))
    shutil.copy2(reference/'assessment.json',out/'baseline-assessment.json')
    samples=[];errors=[];stop=threading.Event();start=time.monotonic()
    def monitor():
        try:
            while not stop.is_set():
                listing=subprocess.check_output(['ps','-axo','pid=,ppid=,rss='],text=True)
                rows=[tuple(map(int,line.split())) for line in listing.splitlines()]
                processes=descendants(rows,os.getpid())
                samples.append(dict(seconds=time.monotonic()-start,rssKiB=sum(rss for pid,rss in processes),processes=len(processes)))
                stop.wait(.5)
        except Exception as exc:errors.append(str(exc))
    limits=dict(max_raw_bytes=2*1024**3,max_compressed_raw_bytes=1024**3,
        max_log_bytes=3*1024**3,max_compressed_log_bytes=512*1024**2,max_log_line_bytes=1024**2)
    (out/'preflight.json').write_text(json.dumps(dict(sources=pinned,inputReceipts=receipts,identities=identities,
        limits=limits,timeoutSeconds=3600,scope='Replay existing complete captures; no simulator execution.'),indent=2)+'\n')
    thread=threading.Thread(target=monitor);thread.start()
    try:
        builders=[lambda fd,source=source,receipt_hash=receipts[name]:
            ([sys.executable,str(Path(__file__).resolve()),'--worker',str(source),'--fd',str(fd),'--receipt-hash',receipt_hash],core)
            for name,source in zip(receipts,sources)]
        result=transport(builders,out/'capture',os.environ.copy(),.00116,3600,**limits)
        captured_seconds=time.monotonic()-start
        reviewed=replay(out/'capture')
        replay_seconds=time.monotonic()-start-captured_seconds
        if result['comparisons']!=[prior['comparisons'][n] for n in ('coarseFine','fineFinest')] or reviewed['comparisons']!=result['comparisons']:
            raise ValueError('Changed complete-window comparison')
        for i,source in enumerate(sources):
            r=json.loads((source/'run.json').read_text())
            if any(result['streams'][i][k]!=r['storage']['waveform.raw'][k] for k in ('sha256','bytes')):
                raise ValueError('Changed full stream identity')
        if {n:sha(HERE/n) for n in SOURCES}!=pinned:raise ValueError('Changed benchmark source')
    finally:
        stop.set();thread.join()
        (out/'resource-samples.json').write_text(json.dumps(dict(samples=samples,errors=errors),indent=2)+'\n')
    if errors or not samples:raise ValueError('Missing resource observations')
    report=dict(completed=True,qualified=False,fullWindowComparisonsExactlyPreserved=True,
        archivedReplayExactlyPreserved=True,captureReplaySeconds=captured_seconds,archiveReviewSeconds=replay_seconds,
        sampledMaximumTreeRssKiB=max(s['rssKiB'] for s in samples),sampleCount=len(samples),
        storageUsage=reviewed['storageUsage'],originalVoltageGate=prior['voltageGate'],inputReceipts=receipts,
        sources=pinned,scope='Complete 1.16-ms exact-tick post-reset refinements replayed through capped retention and rereviewed from new archives. Sampled process-tree RSS includes replay producers and subsequent archive review; not an exact peak or simulator runtime. No full-repeat execution or convergence claim.',
        evidenceLocation=str(out),retention='Full compressed output archives remain at evidenceLocation; hashes alone do not replace them.')
    (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('originalVoltageGate','sources','inputReceipts')},indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out',type=Path);p.add_argument('--worker',type=Path);p.add_argument('--fd',type=int);p.add_argument('--receipt-hash')
    a=p.parse_args()
    if a.worker:worker(a.worker,a.fd,a.receipt_hash)
    elif a.out:run(a.out)
    else:p.error('Need --out')
