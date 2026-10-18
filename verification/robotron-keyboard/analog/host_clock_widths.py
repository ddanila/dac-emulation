#!/usr/bin/env python3
"""Screen host receive-clock pulse widths at an explicit, uncalibrated threshold."""
import argparse
import json
import math
import re
from pathlib import Path
from compare_firmware_io import load_run, sha
from receiver_margins import timestamp_uncertainty
from trace_io import open_text

HERE=Path(__file__).resolve().parent


def widths(samples, timing, threshold=1.4):
    if not math.isfinite(threshold):
        raise ValueError('Invalid threshold')
    result={'qualified':False,'thresholdVolts':threshold,'measurements':[],'censoredIntervals':[]}
    previous=None
    start=None
    last_rise=None
    count=0
    def record(kind,a,b):
        minimum=timing[{'high':'highWidthMinimumSeconds','low':'lowWidthMinimumSeconds','period':'periodMinimumSeconds'}[kind]]
        low=max(0,b[0]-a[1]);high=max(0,b[1]-a[0])
        result['measurements'].append({'kind':kind,'startBracketSeconds':a,'endBracketSeconds':b,
            'durationLowerSeconds':low,'durationUpperSeconds':high,'referenceMinimumSeconds':minimum,
            'status':'pass' if low>=minimum else 'fail' if high<minimum else 'indeterminate'})
    for t,v,uncertainty in samples:
        if not all(map(math.isfinite,(t,v,uncertainty))) or uncertainty<0 or (previous and t<=previous[0]):
            raise ValueError('Invalid or unordered samples')
        level=v>=threshold
        if previous and level != previous[1]:
            bracket=[previous[0]-previous[2],t+uncertainty]
            if start is None:
                result['censoredIntervals'].append({'side':'left','level':'high' if previous[1] else 'low'})
            else:record('high' if previous[1] else 'low',start,bracket)
            start=bracket
            if level:
                if last_rise is not None:record('period',last_rise,bracket)
                last_rise=bracket
        previous=(t,level,uncertainty);count+=1
    if count<2:raise ValueError('Insufficient clock samples')
    result['censoredIntervals'].append({'side':'right' if start is not None else 'both','level':'high' if previous[1] else 'low'})
    kinds={x['kind']for x in result['measurements']}
    result['screenPassed']=kinds=={'high','low','period'} and all(x['status']=='pass'for x in result['measurements'])
    result['samples']=count
    return result


def clock_samples(path, step, end, *, start=0, board=False):
    if not all(map(math.isfinite,(step,start,end))) or step<=0 or not 0<=start<end:
        raise ValueError('Invalid receiver capture window or timestep')
    previous=None
    with open_text(path)as stream:
        header=stream.readline().split()
        columns=5 if board else 3
        if (len(header)!=columns or header[0]!='time'
                or header[-2:]!=['v(receiver_data)','v(receiver_clock)']):
            raise ValueError('Unexpected host receiver trace columns')
        for line in stream:
            tokens=line.split();row=list(map(float,tokens))
            if len(row)!=columns or not all(map(math.isfinite,row)):
                raise ValueError('Invalid receiver row')
            t=row[0];uncertainty=timestamp_uncertainty(tokens[0],t)
            if previous is None:
                if not start <= t <= start+(step*1e-9 if board else 0)+uncertainty:
                    raise ValueError('Missing capture start')
            elif not 0<t-previous[0]<=step*1e-9+uncertainty+previous[1]:
                raise ValueError('Receiver capture time order or gap')
            previous=(t,uncertainty)
            yield t,row[-1],uncertainty
    if previous is None or abs(previous[0]-end)>1e-12:
        raise ValueError('Incomplete receiver capture')


def board_clock_capture(directory):
    from host_input_review import board_capture
    report, start, end, step = board_capture(directory)
    if sha(directory/'trace.txt') != report.get('traceSha256'):
        raise ValueError('Board receiver trace differs or is incomplete')
    return report, start, end, step


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path);p.add_argument('--out',type=Path,required=True)
    p.add_argument('--threshold-volts',type=float,default=1.4)
    p.add_argument('--board',action='store_true',help='Review only the closed-board capture window')
    args=p.parse_args();args.out.unlink(missing_ok=True)
    if args.board:
        report, start, end, step = board_clock_capture(args.run)
    else:
        report,_=load_run(args.run)
        if not report['assumptions'].get('hostBuffer') or report.get('qualified') is not False:
            raise ValueError('Requires experimental host-buffer service capture')
        duration=re.findall(r'^\.?tran [0-9.eE+-]+n ([0-9.eE+-]+)n$',(args.run/'io.cir').read_text(),re.M)
        if len(duration)!=1:raise ValueError('Unexpected service analysis duration')
        start,end,step=0,float(duration[0])*1e-9,report['assumptions']['stepNs']
    limits=json.loads((HERE/'u856_limits.json').read_text())
    result={'qualified':False,'scope':__doc__,'producerReportSha256':sha(args.run/'report.json'),
            'traceSha256':report['traceSha256'],'sources':{name:sha(HERE/name)for name in
                ('host_clock_widths.py','host_input_review.py','u856_limits.json','receiver_margins.py','compare_firmware_io.py','trace_io.py','transient_analysis.py','failure_evidence.py')},
            'boundary':'Sample-bracket screen at an assumed threshold, not U856 Schmitt calibration or between-sample pulse proof. Initial/final censored intervals, supply applicability and system-clock/data-rate ratio are not qualified.',
            'producerPassed':report.get('passed') is True,'producerError':report.get('error'),
            'captureWindowSeconds':[start,end], 'board':args.board,
            'observation':widths(clock_samples(args.run/'trace.txt',step,end,start=start,board=args.board),
                                 limits['serialReceiveClock'],args.threshold_volts)}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(args.out)


if __name__=='__main__':main()
