#!/usr/bin/env python3
"""Retain full drain-review provenance and complete firmware timing records."""
import argparse,collections,hashlib,json,math,shutil
from decimal import Decimal
from pathlib import Path
from ttl7406_probe import sha
from trace_io import open_binary
from postreset_refinement_review import voltage_gate
HERE=Path(__file__).resolve().parent
PAIRS=[('disabled','baseline','off'),('exactTick','off','tick'),('outputDrain','tick','coarse'),('enabledEffect','off','coarse'),('coarseFine','coarse','fine'),('fineFinest','fine','finest'),('forcedRetry','coarse','retry')]

def file_sha(path):
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(4*1024*1024),b''):digest.update(block)
    return digest.hexdigest()

def review(root):
    result=json.loads((root/'full-review.json').read_text());job=json.loads((root/'review-job.json').read_text());retention=json.loads((root/'retention.json').read_text())
    if job['state']!='reviewed' or result['reviewerSha256']!=sha(HERE/'postreset_drain_review.py'):raise ValueError('Unfinished or changed full reviewer')
    if any(sha(HERE/n)!=h for n,h in job['sources'].items()):raise ValueError('Changed full-review source')
    if set(result['comparisons'])!={n for n,_,_ in PAIRS} or not result['completed'] or result['qualified'] or not result['disabledControlPassed']:raise ValueError('Incomplete full drain review')
    original=json.loads((HERE/'reports/postreset-drain-refinements/assessment.json').read_text())
    for name in ('coarseFine','fineFinest'):
        if result['comparisons'][name]!=original['comparisons'][name]:raise ValueError('Changed retained full refinement result')
    gate=voltage_gate(result['comparisons']['coarseFine'],result['comparisons']['fineFinest'])
    if result['voltageGate']!=gate or result['refinementGatePassed']!=(gate['passed'] and result['firmwareRecordsExactlyEqual']['coarseFine'] and result['firmwareRecordsExactlyEqual']['fineFinest']):raise ValueError('Changed convergence gate')
    firmware={};receipts={}
    for name in ('baseline','off','tick','coarse','fine','finest','retry'):
        receipt=json.loads((root/name/'run.json').read_text());receipts[name]=receipt
        expected=result['baselineReceiptSha256'] if name=='baseline' else result['receipts'][name]
        if sha(root/name/'run.json')!=expected or not receipt['completed'] or receipt.get('error') or receipt['exitCode']:raise ValueError('Changed completed receipt')
        if receipt['endSeconds']!=.00116:raise ValueError('Shortened full window')
        for p,h in receipt['inputs'].items():
            if sha(root/name/p)!=h:raise ValueError('Changed retained input')
        records=(root/name/'firmware.txt').read_text().splitlines();firmware[name]=records
        counts=dict(collections.Counter(line.split()[0] for line in records))
        if counts!=result['logs'][name]['firmwareCounts']:raise ValueError('Incomplete firmware extraction')
        item=retention[name]
        if item['logicalLogSha256']!=receipt['log']['sha256'] or item['logicalLogBytes']!=receipt['log']['bytes'] or item['firmwareSha256']!=sha(root/name/'firmware.txt'):raise ValueError('Unbound full log extraction')
    changes={}
    for name,left,right in PAIRS:
        a,b=firmware[left],firmware[right];exact=a==b
        if exact!=result['firmwareRecordsExactlyEqual'][name]:raise ValueError('Firmware equality disagrees with full review')
        comparison=result['comparisons'][name]
        if comparison['endSeconds']!=.00116 or len(comparison['signals'])!=31:raise ValueError('Incomplete full waveform comparison')
        if name=='disabled':
            if not comparison['allSamplesExactlyEqual'] or comparison['samples']!=result['logs']['baseline']['count']:raise ValueError('Invalid disabled control')
        else:
            if comparison['unionKnots']<1_000_000:raise ValueError('Incomplete absolute-time comparison')
            for entry in comparison['signals'].values():
                if not math.isfinite(entry['maximumAbsoluteDifference']) or entry['maximumAbsoluteDifference']<0 or not 0<=entry['timeSeconds']<=.00116:raise ValueError('Invalid comparison maximum')
        rows=[];payload_equal=len(a)==len(b);edge_deltas=[]
        for i in range(max(len(a),len(b))):
            x=a[i] if i<len(a) else None;y=b[i] if i<len(b) else None
            if x==y:continue
            xx=x.split() if x else [];yy=y.split() if y else []
            timing_only=len(xx)>=2 and len(yy)>=2 and xx[0]==yy[0] and xx[2:]==yy[2:] and xx[0] in ('FIRST_FETCH','BUS_EDGE_PS','BUS_SAMPLE','BUS_DRIVE','BUS_LATCH')
            payload_equal &= timing_only
            row=dict(index=i,left=x,right=y,timingFieldOnly=timing_only)
            if timing_only and xx[0]=='BUS_EDGE_PS':
                delta=Decimal(yy[1])-Decimal(xx[1]);row['deltaPicoseconds']=str(delta);edge_deltas.append(abs(delta))
            rows.append(row)
        changes[name]=dict(exactlyEqual=exact,recordCounts=[len(a),len(b)],payloadsEqualIgnoringLoggedTime=payload_equal,changedRecords=rows,maximumBusEdgeShiftPicoseconds=str(max(edge_deltas,default=Decimal(0))))
    return dict(qualified=False,fullReviewCompleted=True,disabledControlPassed=True,refinementGatePassed=result['refinementGatePassed'],voltageGate=gate,firmwareChanges=changes,
                scope='Replays retained full-review metadata and every extracted firmware record, with complete-log hashes verified during extraction. Full waveform comparisons were executed by the original pinned reviewer; this metadata replay is not a new waveform replay. Full compressed waveforms/logs remain local at retained archive identities. Absolute timing differences are reported, not aligned or accepted as convergence.')

def run(local,out):
    local=local.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    shutil.copyfile(local/'postreset-drain-assessment.json',out/'full-review.json');shutil.copyfile(local/'postreset-drain-job.json',out/'review-job.json');retention={}
    for name in ('baseline','off','tick','coarse','fine','finest','retry'):
        source=local/('postreset-adc-on-25' if name=='baseline' else 'postreset-drain-'+name);folder=out/name;folder.mkdir();receipt=json.loads((source/'run.json').read_text())
        for filename in (*receipt['inputs'],'run.json'):
            shutil.copyfile(source/filename,folder/filename)
        for filename in ('candidate-build.json','bounded-assessment.json'):
            if (source/filename).exists():shutil.copyfile(source/filename,folder/filename)
        digest=hashlib.sha256();size=0;records=[]
        with open_binary(source/'ngspice.log') as stream:
            for raw in stream:
                digest.update(raw);size+=len(raw)
                line=raw.decode('utf-8').strip()
                if line.startswith(('FIRST_FETCH ','BUS_','SERIAL_')):records.append(line)
        if digest.hexdigest()!=receipt['log']['sha256'] or size!=receipt['log']['bytes']:raise ValueError('Changed full source log')
        (folder/'firmware.txt').write_text('\n'.join(records)+'\n')
        archives={}
        for filename in ('ngspice.log.xz','waveform.raw.xz'):
            p=source/filename;archives[filename]=dict(path=str(p),bytes=p.stat().st_size,sha256=file_sha(p))
        retention[name]=dict(archives=archives,logicalLogBytes=size,logicalLogSha256=digest.hexdigest(),firmwareSha256=sha(folder/'firmware.txt'))
        print(name,'firmware records',len(records),flush=True)
    (out/'retention.json').write_text(json.dumps(retention,indent=2)+'\n');(out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--local',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.local,a.out)
