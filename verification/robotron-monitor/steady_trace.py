"""Export one completed circuit field for diagnostic optical replay.

This preserves voltages and solved winding/current samples. It cannot establish
warm settling or promote a diagnostic image to an accepted steady-state frame.
"""
import csv
import hashlib
import json
import math
from pathlib import Path
import beam_render
import steady_supply

PROBES=('v(eht)','v(g2)','v(g4)','v(cathode)','i(lhorizontal)',
        'i(lvertical)','i(@b.xcrt.bbeam[i])')


def export(raw, output, *, start_s, end_s):
    if not all(math.isfinite(t) for t in (start_s,end_s)) or not 0<=start_s<end_s:
        raise ValueError('invalid requested field')
    raw=Path(raw);out=Path(output)
    with raw.open('rb') as stream:before=hashlib.file_digest(stream,'sha256').hexdigest()
    previous=None;count=0;first=last=None
    with out.open('x',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(beam_render.FIELDS)
        def write(t,values):
            nonlocal count,first,last
            if values[-1]<-1e-12:raise ValueError('negative gun entrance beam current')
            # Round-off below zero is not emitted charge.
            values=(*values[:-1],max(values[-1],0.))
            writer.writerow((t-start_s,*values));count+=1
            if first is None:first=t
            last=t
        for row in steady_supply.raw_rows(raw):
            t=row['time'];v=tuple(row[p] for p in PROBES)
            if previous is not None:
                pt,pv=previous
                for boundary in (start_s,end_s):
                    if pt<boundary<=t and (last is None or boundary>last):
                        f=(boundary-pt)/(t-pt)
                        write(boundary,tuple(a+f*(b-a) for a,b in zip(pv,v)))
            if start_s<=t<end_s and (last is None or t>last):write(t,v)
            previous=t,v
        if first!=start_s or last!=end_s or count<2:raise ValueError('raw trace does not contain complete requested field')
    with raw.open('rb') as stream:
        if hashlib.file_digest(stream,'sha256').hexdigest()!=before:raise ValueError('raw circuit trace changed during export')
    with out.open('rb') as stream:result_hash=hashlib.file_digest(stream,'sha256').hexdigest()
    report=dict(format='dac-steady-field-trace-v1',status='complete',
        qualification='diagnostic-connected-circuit-field',raw_sha256=before,
        trace_sha256=result_hash,original_start_s=start_s,original_end_s=end_s,
        trace_start_s=0,trace_end_s=end_s-start_s,rows=count,
        electrical_settling_verified=False,full_monitor_qualified=False,specimen_validated=False,
        probe_mapping=dict(zip(beam_render.FIELDS[1:],PROBES)),
        limitations=['B31G22 gun entrance current follows the bounded electrothermal load; trajectory interception is not fed back to each electrode.',
                     'This exporter does not establish source provenance, synchronization, numerical refinement or periodic state.'])
    out.with_suffix('.json').write_text(json.dumps(report,indent=2)+'\n')
    return report


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--raw',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--start',type=float,required=True,help='Original circuit time in seconds')
    parser.add_argument('--end',type=float,required=True,help='Original circuit time in seconds')
    args=parser.parse_args()
    print(json.dumps(export(args.raw,args.output,start_s=args.start,end_s=args.end),indent=2))
