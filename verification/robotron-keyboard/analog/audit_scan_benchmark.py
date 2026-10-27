#!/usr/bin/env python3
"""Check a full retained scan and time equivalent scanner paths on a bounded sample."""
import argparse,json,platform,resource,tempfile,time
from pathlib import Path
import audit_log
import fast_audit_log
from retained_evidence import check
from trace_io import open_text
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def run(root,mode,out,sample_lines=20000):
    if not 1<=sample_lines<=100000:raise ValueError('Sample must contain 1..100000 lines')
    check(root)
    folder=root/mode;receipt=json.loads((folder/'run.json').read_text())
    if not receipt.get('completed') or receipt.get('error') or 'summary' not in receipt:raise ValueError('Need completed retained scan receipt')
    start=time.monotonic();result=fast_audit_log.complete(folder/'ngspice.log');elapsed=time.monotonic()-start
    if result!=receipt['summary']:raise ValueError('Changed full scan result')
    with tempfile.TemporaryDirectory() as d:
        sample=Path(d)/'sample.log';count=0
        with open_text(folder/'ngspice.log') as stream,sample.open('w') as target:
            for line in stream:
                if count==sample_lines:break
                target.write(line);count+=1
        results={};times={}
        for name,module in [('original',audit_log),('prefilter',fast_audit_log)]:
            start=time.monotonic();results[name]=module.scan(sample);times[name]=time.monotonic()-start
        if results['original']!=results['prefilter']:raise ValueError('Changed sample scan result')
    log=folder/'ngspice.log.xz'
    evidence=dict(qualified=False,fullRetainedScanExactlyMatchesOriginalReceipt=True,fullScanSeconds=elapsed,
                  fullLogicalBytes=receipt['log']['bytes'],sampleLines=count,sampleScanSeconds=times,
                  prefilterActive=fast_audit_log.SUPPORTED,peakResidentBytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1 if platform.system()=='Darwin' else 1024),
                  platform=platform.platform(),retainedRoot=str(root),mode=mode,manifestSha256=sha(root/'manifest.json'),receiptSha256=sha(folder/'run.json'),compressedLogSha256=sha(log),
                  sourceHashes={**fast_audit_log.SUPPORTED_SOURCES,**{n:sha(HERE/n) for n in ('fast_audit_log.py','audit_scan_benchmark.py')}},
                  scope='Exact scan-result equivalence on a complete retained log; timing on this host is observational, not a portable performance bound. All lines remain processed and numerical/state gates are unchanged.')
    with out.open('x') as f:json.dump(evidence,f,indent=2);f.write('\n')
    print(json.dumps(evidence,indent=2),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('root','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--mode',choices=('baseline','off','observe'),default='observe');p.add_argument('--sample-lines',type=int,default=20000)
    a=p.parse_args();run(a.root,a.mode,a.out,a.sample_lines)
