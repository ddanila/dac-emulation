"""Measure electrical grid calibration quantities from a completed raw trace.

Retrace is the shorter monotone excursion between the extrema of the
line-averaged horizontal yoke current. Averaging all lines in the final field
suppresses switching ripple without treating a collector pulse as beam motion.
"""
import argparse
import json
import math
from pathlib import Path

import steady_supply


def measure(trace, *, start_s, end_s, line_s, phase_bins=256):
    if (not all(math.isfinite(x) for x in (start_s,end_s,line_s))
            or start_s<0 or end_s<=start_s or line_s<=0
            or type(phase_bins) is not int or phase_bins<64 or phase_bins>4096):
        raise ValueError('invalid calibration measurement window')
    lines=round((end_s-start_s)/line_s)
    if lines<32 or not math.isclose(lines*line_s,end_s-start_s,rel_tol=0,abs_tol=1e-9):
        raise ValueError('calibration field does not contain complete lines')
    sums=[0.]*phase_bins;count=lines*phase_bins
    previous=None;first=last=None;sample_index=0;eht_integral=0.
    for row in steady_supply.raw_rows(trace):
        t=row['time']
        if first is None:first=t
        last=t
        if 'v(eht)' not in row or 'i(lhorizontal)' not in row:
            raise ValueError('calibration trace lacks EHT or horizontal yoke probe')
        if previous is not None:
            a=max(previous['time'],start_s);b=min(t,end_s)
            if b>a:
                fraction_a=(a-previous['time'])/(t-previous['time'])
                fraction_b=(b-previous['time'])/(t-previous['time'])
                va=previous['v(eht)']+fraction_a*(row['v(eht)']-previous['v(eht)'])
                vb=previous['v(eht)']+fraction_b*(row['v(eht)']-previous['v(eht)'])
                eht_integral+=(va+vb)*.5*(b-a)
            while sample_index<count:
                phase=sample_index%phase_bins
                target=start_s+sample_index//phase_bins*line_s+(phase+.5)*line_s/phase_bins
                if target>t:break
                if target<previous['time']:
                    raise ValueError('calibration trace has a missing phase interval')
                fraction=(target-previous['time'])/(t-previous['time'])
                sums[phase]+=previous['i(lhorizontal)']+fraction*(row['i(lhorizontal)']-previous['i(lhorizontal)'])
                sample_index+=1
        previous=row
    if (first is None or abs(first)>1e-12 or not math.isclose(last,end_s,rel_tol=0,abs_tol=1e-9)
            or sample_index!=count):
        raise ValueError('calibration trace does not span the completed grid solve')
    wave=[x/lines for x in sums]
    radius=max(1,round(phase_bins*.008))
    smooth=[sum(wave[(i+j)%phase_bins] for j in range(-radius,radius+1))/(2*radius+1)
            for i in range(phase_bins)]
    maximum=max(range(phase_bins),key=smooth.__getitem__)
    minimum=min(range(phase_bins),key=smooth.__getitem__)
    swing=smooth[maximum]-smooth[minimum]
    if not math.isfinite(swing) or swing<.01:
        raise ValueError('horizontal yoke current has no measurable scan swing')
    forward=(minimum-maximum)%phase_bins
    if forward==0 or forward==phase_bins//2:
        raise ValueError('horizontal yoke waveform has no distinct retrace excursion')
    def variation(start,steps):
        return sum(abs(smooth[(start+i+1)%phase_bins]-smooth[(start+i)%phase_bins])
                   for i in range(steps))
    if (variation(maximum,forward)>1.25*swing
            or variation(minimum,phase_bins-forward)>1.25*swing):
        raise ValueError('horizontal yoke waveform is not a monotone scan and retrace')
    retrace_us=min(forward,phase_bins-forward)*line_s/phase_bins*1e6
    return dict(eht_mean_v=eht_integral/(end_s-start_s),
                horizontal_retrace_us=retrace_us,horizontal_yoke_swing_a=swing,
                retrace_method='shorter-extrema-arc-of-line-averaged-yoke-current',
                line_count=lines,phase_bins=phase_bins)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',type=Path,required=True)
    parser.add_argument('--start',type=float,required=True)
    parser.add_argument('--end',type=float,required=True)
    parser.add_argument('--line-s',type=float,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=measure(args.trace,start_s=args.start,end_s=args.end,line_s=args.line_s)
    with args.output.open('x') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':main()
