#!/usr/bin/env python3
"""Decompose reported peak differences relative to a retained fine PWL curve."""
import argparse
import json
from decimal import Decimal as D, localcontext
from pathlib import Path
from refinement_peak_review import review, witnesses
from compare_firmware_io import sha

HERE=Path(__file__).resolve().parent


def decompose(time, grid_value, reference_value, endpoints, reference_endpoints):
    with localcontext() as context:
        context.prec=64
        a,b=map(D.from_float,endpoints)
        if not a<=D.from_float(time)<=b or a==b:raise ValueError('Invalid interpolation bracket')
        ratio=(D.from_float(time)-a)/(b-a)
        resampled=D(reference_endpoints[0])+ratio*(D(reference_endpoints[1])-D(reference_endpoints[0]))
        endpoint=D(grid_value)-resampled
        sampling=resampled-D(reference_value)
        total=D(grid_value)-D(reference_value)
        return {'signedTotalVolts':str(total),'endpointValueContributionVolts':str(endpoint),
                'referenceCurveSamplingContributionVolts':str(sampling),
                'identityResidualVolts':str(total-endpoint-sampling)}


def build(root,evidence,prefix):
    peaks=review(root,evidence,prefix)
    requests={name:[] for name in peaks['rawCaptureSha256']}
    for peak in peaks['peaks']:
        for grid,reference in (('coarse','fine'),('fine','coarse')):
            for endpoint,(time,_) in enumerate(peak[grid+'Witness']['bracket']):
                requests[peak[reference]].append({'id':f"{peak['id']}:{grid}:{endpoint}",'signal':peak['signal'],'timeSeconds':time})
    captured={}
    for name,pending in requests.items():
        if not pending:continue
        path=root/(prefix+name)/'network_witness.txt'
        if sha(path)!=peaks['rawCaptureSha256'][name]:raise ValueError('Changed capture between passes')
        run=json.loads((evidence/name/'run.json').read_text())
        captured[name]=witnesses(path,run['observationSignals'],run['stepNs'],pending)
    for peak in peaks['peaks']:
        peak['decompositions']=[]
        for grid,reference in (('coarse','fine'),('fine','coarse')):
            endpoints=[captured[peak[reference]][f"{peak['id']}:{grid}:{i}"] for i in range(2)]
            peak['decompositions'].append({'grid':grid,'referenceCurve':reference,'referenceAtGridEndpoints':endpoints,
                **decompose(peak['timeSeconds'],peak[grid+'Witness']['interpolatedValue'],
                    peak[reference+'Witness']['interpolatedValue'],[p[0] for p in peak[grid+'Witness']['bracket']],
                    [e['interpolatedValue'] for e in endpoints])})
    for name,digest in peaks['rawCaptureSha256'].items():
        if sha(root/(prefix+name)/'network_witness.txt')!=digest:raise ValueError('Changed capture after review')
    peaks['runDirectoryPrefix']=prefix
    peaks['sources']['sampling_error_review.py']=sha(HERE/'sampling_error_review.py')
    peaks['scope']='Algebraic decomposition of each retained whole-window voltage maximum: C(t)-F(t) = C(t)-I_C[F](t) + I_C[F](t)-F(t), where I_C samples the fine piecewise-linear curve at the enclosing coarse knots. Both reference directions are retained. The second term measures resampling of the selected curve; the first retains endpoint-value disagreement, which can itself include interpolation of the reference. Attribution depends on the reference direction and signed cancellation is preserved. The fine curve is not ground truth, so neither term bounds physical error or justifies subtracting anything from acceptance. No time alignment or omitted peak.'
    return peaks


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runs',type=Path,required=True);p.add_argument('--evidence',type=Path,required=True);p.add_argument('--prefix',required=True);p.add_argument('--out',type=Path,required=True);args=p.parse_args()
    args.out.write_text(json.dumps(build(args.runs,args.evidence,args.prefix),indent=2)+'\n')
