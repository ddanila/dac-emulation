#!/usr/bin/env python3
"""Review the disabled control and matched exact-capacitor refinement attempts."""
import argparse
import json
from pathlib import Path
import sys

ANALOG=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ANALOG))
import hashlib

def sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda:stream.read(1024*1024), b''):digest.update(chunk)
    return digest.hexdigest()

from compare_mpfr_replays import compatible, step_and_normalized
from host_waveform_comparison import rows, compare_samples


def load(path, mode):
    report=json.loads((path/'report.json').read_text())
    receipt=json.loads((path/'assembly-control.json').read_text())
    if receipt['mode']!=mode or receipt['reportSha256']!=sha(path/'report.json'):
        raise ValueError('Correction mode or producer differs')
    for name,digest in report['artifacts'].items():
        if sha(path/name)!=digest:raise ValueError('Changed producer artifact: '+name)
    interruption=path/'interruption.json'
    if report.get('error') and (not interruption.exists() or receipt.get('interruptionSha256')!=sha(interruption)):
        raise ValueError('Unexplained incomplete replay review')
    if report['timeStepMode']!='represented' or report['integrationArithmetic']!='256' or report['integration']['selection']!='original':
        raise ValueError('Expected represented-time trapezoidal MPFR256 integration')
    if receipt['completed']!=report['completed']:raise ValueError('Receipt completion differs')
    if mode=='off' and not receipt['disabledControlPassed']:raise ValueError('Disabled control did not reproduce baseline')
    step,deck=step_and_normalized((path/'io.cir').read_text())
    return {'report':report,'receipt':receipt,'stepNs':step,'normalizedDeck':deck}


def logged_tail(path):
    last={}
    with path.open() as stream:
        for line in stream:
            if line.startswith('TRUNC_AUDIT solver '):
                f=dict(item.split('=',1) for item in line.split()[2:])
                last={'timeSeconds':float.fromhex(f['time']), 'deltaSeconds':float.fromhex(f['delta']),
                      'order':int(f['order']), 'newtonResult':int(f['result'])}
    return last


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('off',type=Path);p.add_argument('coarse',type=Path);p.add_argument('fine',type=Path)
    p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    control,coarse,fine=[load(path,mode) for path,mode in [(a.off,'off'),(a.coarse,'exact'),(a.fine,'exact')]]
    compatible(coarse,fine,'timestep')
    for field in ('ngspiceRuntime','sourceReportSha256','stopSeconds','mode'):
        if control['report'][field]!=coarse['report'][field]:raise ValueError('Disabled control differs: '+field)
    if control['normalizedDeck']!=coarse['normalizedDeck'] or control['stepNs']!=coarse['stepNs']:
        raise ValueError('Disabled control circuit or step differs')
    if control['report']['artifacts']['build-provenance.json']!=coarse['report']['artifacts']['build-provenance.json']:
        raise ValueError('Disabled control build provenance differs')
    for key in ('assemblyPatchSha256','assemblyHeaderSha256'):
        if len({r['receipt'][key] for r in (control,coarse,fine)})!=1:raise ValueError('Correction identity differs')
    result={'completed':True,'qualified':False,'scope':__doc__,'disabledControlPassed':True,
            'pairCompleted':all(r['report']['completed'] for r in (coarse,fine)),
            'runs':{label:{'producerReportSha256':sha(path/'report.json'),
                          'receiptSha256':sha(path/'assembly-control.json'),
                          'stepNs':capture['stepNs'],'completed':capture['report']['completed'],
                          'solverDiagnostic':capture['report']['solverDiagnostic'],
                          'precisionGuardDiagnostics':capture['report']['precisionGuardDiagnostics'],
                          'producerError':capture['report'].get('error'),
                          'interruption':json.loads((path/'interruption.json').read_text()) if (path/'interruption.json').exists() else None,
                          'waveforms':capture['report']['waveforms'],
                          'lastLoggedTrial':logged_tail(path/'ngspice.log')}
                    for label,path,capture in [('off',a.off,control),('coarse',a.coarse,coarse),('fine',a.fine,fine)]},
            'sources':{str(p.relative_to(ANALOG)):sha(p) for p in [Path(__file__),ANALOG/'compare_mpfr_replays.py',ANALOG/'host_waveform_comparison.py',ANALOG/'analog_driver_replay.py']},
            'boundary':'Constant-capacitor local corrections only. Other stamp additions, nonlinear-device evaluation and stored histories remain binary64. Matched attempts are not a completed refinement pair unless both reach the requested stop. Even a completed analog-only segment does not qualify the full coupled board or device dynamics.'}
    if result['pairCompleted']:
        headers=[]
        for path,capture in [(a.coarse,coarse),(a.fine,fine)]:
            if capture['report']['solverDiagnostic']:raise ValueError('Completed capture has solver diagnostic')
            with (path/'host-trace.txt').open() as stream:headers.append(stream.readline().split()[1:])
            if any(abs(v['lastSampleSeconds']-capture['report']['stopSeconds'])>1e-15 for v in capture['report']['waveforms'].values()):
                raise ValueError('Completed capture lacks full extent')
        if headers[0]!=headers[1]:raise ValueError('Observation nodes differ')
        comparison=compare_samples(rows(a.coarse/'host-trace.txt',headers[0],coarse['stepNs']),rows(a.fine/'host-trace.txt',headers[1],fine['stepNs']))
        for name,entry in zip(headers[0],comparison['signals']):entry['signal']=name
        result['absoluteTimeVoltages']=comparison
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(a.out)

if __name__=='__main__':main()
