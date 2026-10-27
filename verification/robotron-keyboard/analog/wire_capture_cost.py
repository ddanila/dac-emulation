#!/usr/bin/env python3
"""Retain measured wire capture costs separately from full semantic acceptance."""
import argparse,json,math,shutil
from pathlib import Path
from ttl7406_probe import sha
from wire_board_budget_review import budgets
HERE=Path(__file__).resolve().parent
MODES=('off','observe','wire4-init-corrupt','wire4-driven-corrupt','wire4-propagate-corrupt','wire8-init-corrupt','wire8-driven-corrupt','wire8-propagate-corrupt')


def review(root):
    identities=json.loads((root/'capture-identities.json').read_text())
    if set(identities)!=set(MODES):raise ValueError('Missing capture identity')
    rows={}
    for mode in MODES:
        path=root/mode/'run.json';r=json.loads(path.read_text());log=r['log'];identity=identities[mode];expected=0 if mode in ('off','observe') else 2
        if sha(path)!=identity['receiptSha256'] or r['producerSha256']!=sha(HERE/'wire_board_budget_capture.py'):raise ValueError('Changed receipt or producer')
        if r.get('completed') is not True or r.get('error') or r['mode']!=mode or r['captureTimeoutSeconds']!=3000 or r['endSeconds']!=20e-6:raise ValueError('Incomplete bounded capture')
        if any(r[k]!=expected for k in ('exitCode','expectedExitCode')) or log['exitCode']!=expected:raise ValueError('Wrong capture exit')
        if log['logicalLimitBytes']!=12*1024**3 or log['compressedLimitBytes']!=256*1024**2:raise ValueError('Changed capture limit')
        for key,cap in (('bytes',12*1024**3),('compressedBytes',256*1024**2)):
            if type(log.get(key)) is not int or not 0<log[key]<=cap:raise ValueError('Exceeded capture limit')
        producer=log['elapsedSeconds'];total=r['elapsedSeconds']
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0 for v in (producer,total)) or producer>3000 or total<producer:raise ValueError('Invalid measured duration')
        if identity['compressedLogBytes']!=log['compressedBytes'] or len(identity['compressedLogSha256'])!=64:raise ValueError('Mismatched compressed log identity')
        rows[mode]=dict(logicalLogBytes=log['bytes'],compressedLogBytes=log['compressedBytes'],producerSeconds=producer,captureAndChecksSeconds=total,logicalCapFraction=log['bytes']/log['logicalLimitBytes'])
    return dict(qualified=False,capturesCompleted=True,semanticAcceptanceEstablished=False,runs=rows,
        totalLogicalLogBytes=sum(r['logicalLogBytes'] for r in rows.values()),totalCompressedLogBytes=sum(r['compressedLogBytes'] for r in rows.values()),
        totalProducerSeconds=sum(r['producerSeconds'] for r in rows.values()),totalCaptureAndChecksSeconds=sum(r['captureAndChecksSeconds'] for r in rows.values()),
        scope='Receipt-backed costs for all eight completed bounded wire captures. Compressed log sizes and hashes were checked against capture files during collection; this report retains receipts and identities, not those logs. Producer time is separate from capture/compression/check time. Full semantic review, exact memory peaks, general runtime/storage bounds and longer-window capacity are not established.')


def collect(source,out):
    source=Path(source);out=Path(out);budgets(source)
    if out.exists():raise ValueError('Existing cost evidence')
    identities={}
    for mode in MODES:
        log=source/mode/'ngspice.log.xz';receipt=source/mode/'run.json'
        identities[mode]=dict(receiptSha256=sha(receipt),compressedLogBytes=log.stat().st_size,compressedLogSha256=sha(log))
    out.mkdir()
    for mode in MODES:
        (out/mode).mkdir();shutil.copyfile(source/mode/'run.json',out/mode/'run.json')
    (out/'capture-identities.json').write_text(json.dumps(identities,indent=2)+'\n')
    result=review(out)
    for mode in MODES:
        identity=identities[mode];log=source/mode/'ngspice.log.xz'
        if sha(source/mode/'run.json')!=identity['receiptSha256'] or sha(log)!=identity['compressedLogSha256']:raise ValueError('Capture changed during cost collection')
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');return result

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();collect(a.source,a.out)
