#!/usr/bin/env python3
"""Retain every full-window delivery record with verified complete-log identity."""
import argparse,hashlib,json,shutil
from pathlib import Path
from trace_io import open_binary
from delivery_audit_review import scan
from postreset_drain_complete_evidence import file_sha
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def review(root):
    original=json.loads((root/'full-review.json').read_text());job=json.loads((root/'review-job.json').read_text());receipt=json.loads((root/'run.json').read_text());retention=json.loads((root/'retention.json').read_text())
    if job['state']!='passed' or any(sha(HERE/n)!=h for n,h in job['sources'].items()):raise ValueError('Unfinished or changed delivery reviewer')
    if not receipt['completed'] or receipt.get('error') or receipt['exitCode']!=0 or receipt['endSeconds']!=.00116:raise ValueError('Incomplete full capture')
    if sha(root/'run.json')!=retention['receiptSha256'] or sha(root/'full-review.json')!=retention['assessmentSha256']:raise ValueError('Changed full review provenance')
    for n,h in receipt['inputs'].items():
        if sha(root/n)!=h:raise ValueError('Changed capture input')
    if retention['logicalLogSha256']!=receipt['log']['sha256'] or retention['logicalLogBytes']!=receipt['log']['bytes']:raise ValueError('Unbound extraction')
    comparison=original['comparison']
    if not comparison['allSamplesExactlyEqual'] or comparison['samples']!=receipt['logSummary']['count'] or comparison['endSeconds']!=.00116 or len(comparison['signals'])!=31 or not original['firmwareRecordsExactlyEqual']:raise ValueError('Incomplete exact comparison')
    audit=scan(root/'delivery.txt')
    if audit!=original['audit']:raise ValueError('Changed complete delivery records')
    firmware=(root/'firmware.txt').read_text()
    if firmware!=(HERE/'reports/postreset-drain-complete/coarse/firmware.txt').read_text():raise ValueError('Changed complete firmware')
    return dict(qualified=False,fullReviewCompleted=True,comparison=comparison,audit=audit,firmwareRecordsExactlyEqual=True,scope='Replays every delivery and firmware record extracted after complete-log hash verification. Original full waveform review passed; this retained metadata/record replay is not a new waveform replay. Full compressed archives remain local. No ADC decision history, clamp correction or convergence qualification.')

def run(local,out):
    source=local/'postreset-delivery-on-25';out.mkdir(exist_ok=False);r=json.loads((source/'run.json').read_text())
    for n in (*r['inputs'],'run.json','candidate-build.json','bounded-assessment.json'):shutil.copyfile(source/n,out/n)
    shutil.copyfile(local/'postreset-delivery-assessment.json',out/'full-review.json');shutil.copyfile(local/'postreset-delivery-job.json',out/'review-job.json');shutil.copyfile(local/'postreset-delivery-job.py',out/'original-review-job.py')
    digest=hashlib.sha256();size=0;delivery=[];firmware=[]
    with open_binary(source/'ngspice.log') as stream:
        for raw in stream:
            digest.update(raw);size+=len(raw);line=raw.decode('utf-8').strip()
            if line.startswith('DELIVERY_AUDIT '):delivery.append(line)
            if line.startswith(('FIRST_FETCH ','BUS_','SERIAL_')):firmware.append(line)
    if digest.hexdigest()!=r['log']['sha256'] or size!=r['log']['bytes']:raise ValueError('Changed complete source log')
    (out/'delivery.txt').write_text('\n'.join(delivery)+'\n');(out/'firmware.txt').write_text('\n'.join(firmware)+'\n')
    archives={}
    for n in ('ngspice.log.xz','waveform.raw.xz'):
        p=source/n;archives[n]=dict(path=str(p.resolve()),bytes=p.stat().st_size,sha256=file_sha(p))
    (out/'retention.json').write_text(json.dumps(dict(archives=archives,logicalLogSha256=digest.hexdigest(),logicalLogBytes=size,receiptSha256=sha(out/'run.json'),assessmentSha256=sha(out/'full-review.json')),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--local',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();run(a.local,a.out)
