#!/usr/bin/env python3
"""Review direct-driver refinement without promoting fitted device physics."""
import argparse
import json
from pathlib import Path

from gate_switching_probe import sha
from network_refinement_review import artifact, events, text_file
from network_refinement_series import series
from network_trace import PHYSICAL_SIGNALS
from host_waveform_comparison import rows

HERE=Path(__file__).resolve().parent


def ranges(path):
    receipt=json.loads((path/'run.json').read_text())
    limits={n:{'minimum':float('inf'),'maximum':-float('inf')} for n in PHYSICAL_SIGNALS}
    for row in rows(path/'network_witness.txt',PHYSICAL_SIGNALS,receipt['stepNs']):
        if row[0]<.001:
            continue
        for name,value in zip(PHYSICAL_SIGNALS,row[1:]):
            result=limits[name]
            if value<result['minimum']:
                result['minimum']=value;result['minimumTimeSeconds']=row[0]
            if value>result['maximum']:
                result['maximum']=value;result['maximumTimeSeconds']=row[0]
    return {'startSeconds':.001,'endSeconds':.00116,'signals':limits,
            'boundary':'Sampled post-reset range, not a static-limit waiver or proof of intersample extrema.'}


def review(paths, baseline, device_report, validation_report):
    device=json.loads(device_report.read_text())
    validation=json.loads(validation_report.read_text())
    if not device['completed'] or not validation['completed']:
        raise ValueError('Incomplete device evidence')
    if validation['calibrationSha256']!=sha(device_report):
        raise ValueError('Different calibrated device')
    for p in paths:
        receipt=json.loads((p/'run.json').read_text())
        if not receipt.get('physicalDriverTrace'):
            raise ValueError('Expected electrical driver observations')
    result=series(paths)
    reference=events(text_file(artifact(baseline,'ngspice.log')))
    live=[result['pairs'][0]['events'][0],result['pairs'][0]['events'][1],result['pairs'][1]['events'][1]]
    return dict(completed=True,qualified=False,boardAdmission=False,representativeTrafficExecuted=False,
        deviceScreensPass=device['cases'][0]['selectedScreensPass'] and validation['allScreensPass'],
        firmwareMatchesIdealDriverReference=all(e['samples']==reference['samples'] for e in live),
        firmwareLatchesMatch=all(e['latchesMatch'] for e in live),
        sampledPostResetRanges=[ranges(p) for p in paths],
        refinement=result,
        sources={p.name:sha(p) for p in (Path(__file__),HERE/'network_refinement_series.py',HERE/'network_refinement_review.py',HERE/'network_trace.py')},
        evidence={'deviceReportSha256':sha(device_report),'validationReportSha256':sha(validation_report),
                  'baselineLogSha256':sha(artifact(baseline,'ngspice.log'))},
        boundary='Within-series physics and stimulus are identical. Comparison with ideal-driver firmware checks logical preservation, not waveform equivalence between different circuits. No trace alignment or excluded transition windows. Storage is fitted to typical values; junction capacitance and CPU I/V remain hypotheses. Representative electrical traffic remains gated on board convergence and model admission.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('runs',nargs=3,type=Path)
    p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--device-report',type=Path,required=True)
    p.add_argument('--validation-report',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    a.out.write_text(json.dumps(review(a.runs,a.baseline,a.device_report,a.validation_report),indent=2)+'\n')
