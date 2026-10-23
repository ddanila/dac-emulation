#!/usr/bin/env python3
"""Compare corrected captures without promoting a failed or truncated pair."""
import argparse,json,sys
from pathlib import Path
A=Path(__file__).resolve().parents[2];sys.path.insert(0,str(A))
from analog_driver_replay import sha
from host_waveform_comparison import rows,compare_samples
from accepted_capture_review import prefix

def capture(path):
    report=json.loads((path/'report.json').read_text());receipt=json.loads((path/'device-control.json').read_text())
    if receipt['reportSha256']!=sha(path/'report.json'):raise ValueError('Changed producer report')
    for name,digest in report['artifacts'].items():
        if sha(path/name)!=digest:raise ValueError('Changed producer artifact: '+name)
    with (path/'host-trace.txt').open() as stream:signals=stream.readline().split()[1:]
    step=50/report['timestep']['divisor'];samples=list(rows(path/'host-trace.txt',signals,step))
    return report,receipt,signals,samples

def main():
    p=argparse.ArgumentParser();p.add_argument('root',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    captures={mode:capture(a.root/('host-device-'+mode)) for mode in ('off','coarse','fine','quarter')}
    if not captures['off'][1]['disabledControlPassed']:raise ValueError('No identical disabled control')
    base=captures['off'][0];results={};pairs={}
    for mode,(r,receipt,signals,samples) in captures.items():
        if r['sourceReportSha256']!=base['sourceReportSha256'] or r['ngspiceRuntime']!=base['ngspiceRuntime']:raise ValueError('Incompatible source/runtime')
        results[mode]={'completed':r['completed'],'operationallyTruncated':receipt['operationallyTruncated'],'solverDiagnostic':r['solverDiagnostic'],'lastSampleSeconds':samples[-1][0],'stepDivisor':r['timestep']['divisor'],'voltageRanges':{s:[min(v[i+1] for v in samples),max(v[i+1] for v in samples)] for i,s in enumerate(signals)},'reportSha256':sha(a.root/('host-device-'+mode)/'report.json'),'controlSha256':sha(a.root/('host-device-'+mode)/'device-control.json')}
    for left,right in [('coarse','fine'),('fine','quarter')]:
        x,y=captures[left],captures[right]
        if x[2]!=y[2]:raise ValueError('Different signal sets')
        end=min(x[3][-1][0],y[3][-1][0]);comparison=compare_samples(prefix(x[3],end),prefix(y[3],end))
        pairs[left+'-'+right]={'bothCompleted':x[0]['completed'] and y[0]['completed'],'commonPrefixOnly':not(x[0]['completed'] and y[0]['completed']),'comparison':dict(comparison,signals={name:value for name,value in zip(x[2],comparison['signals'])})}
    result={'completed':True,'qualified':False,'disabledControlPassed':True,'runs':results,'pairs':pairs,'sources':{name:sha(A/name) for name in ['reports/host-device-additions/assess.py','host_waveform_comparison.py','accepted_capture_review.py']},'boundary':'Same circuit parameters and binary64 nonlinear evaluations; correction additionally preserves BJT/diode matrix and RHS accumulation. Absolute-time comparison, no phase alignment. Completing this short analog replay does not qualify full firmware runs, device dynamics, startup or electrical limits.'}
    a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:{'completed':r['completed'],'lastSampleSeconds':r['lastSampleSeconds']} for k,r in results.items()},indent=2))
if __name__=='__main__':main()
