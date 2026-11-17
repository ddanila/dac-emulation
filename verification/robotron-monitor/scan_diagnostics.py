"""Separate sparse native VIDEO, scan extent and illuminated beam extent.

Uniform phase samples characterize the raster; they are not a substitute for
full-bandwidth optical integration. Logical pixels are a validation reference.
"""
import argparse
import bisect
import collections
import hashlib
import json
import math
from pathlib import Path
import beam_render
import lab
import phosphor
import steady_supply
import trajectory_native


def source_summary(selection, width=864):
    period=selection['period_ticks'];line=selection['line_period_ticks']
    height=round(period/line)
    if type(width) is not int or not 1<=width<=4096 or height<1 or abs(period/line-height)>1e-6:
        raise ValueError('logical reference requires an integer-line field and bounded width')
    pixels=bytearray(width*height);active=[0.]*height
    events=selection['events']
    for a,b in zip(events,events[1:]+[[period,0,0,0]]):
        if not a[1]:continue
        lo=a[0];end=min(b[0],period)
        while lo<end:
            row=min(height-1,int(lo//line));hi=min(end,(row+1)*line)
            active[row]+=(hi-lo)/selection['clock_hz']
            x0=max(0,int((lo-row*line)*width/line))
            x1=min(width,math.ceil((hi-row*line)*width/line))
            pixels[row*width+x0:row*width+x1]=bytes([255])*(x1-x0)
            lo=hi
    occupied=[i for i,x in enumerate(active) if x]
    return dict(width=width,height=height,active_lines=occupied,
        active_video_s=sum(active),active_video_s_per_line=active,
        field_s=period/selection['clock_hz'],line_s=line/selection['clock_hz'],
        qualification='logical-timing-reference-not-CRT-output'),pixels


def phase_samples(trace, count=4096, expected_period=None):
    rows=beam_render.read_trace(trace)
    start,end=rows[0][0],rows[-1][0]
    if expected_period is not None and (abs(start)>1e-12 or abs(end-expected_period)>1e-10):
        raise ValueError('diagnostics require one complete zero-origin selected field')
    j=0
    for i in range(count):
        t=start+(end-start)*(i+.5)/count
        while rows[j+1][0]<t:j+=1
        a,b=rows[j:j+2];f=(t-a[0])/(b[0]-a[0])
        yield tuple(x+f*(y-x) for x,y in zip(a,b))


def bounds(points):
    if not points:return None
    xs,ys=zip(*points)
    return dict(x_min_m=min(xs),x_max_m=max(xs),y_min_m=min(ys),y_max_m=max(ys),
                width_m=max(xs)-min(xs),height_m=max(ys)-min(ys))


def plot(path, samples):
    """Self-contained diagnostic SVG; each labelled panel has its own SI scale."""
    panels=[('Yoke currents (A)',(5,6),('horizontal','vertical')),
            ('Anode relative to cathode (V)',(1,),('anode',)),
            ('Gun electrodes relative to cathode (V)',(2,3),('grid 2','focus')),
            ('Gun entrance current (A)',(7,),('emission',)),
            ('Beam landing coordinates (m)',(8,9),('horizontal','vertical'))]
    colors=['#1670b7','#ca5421','#72820e'];parts=['<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1020" viewBox="0 0 1000 1020"><rect width="1000" height="1020" fill="white"/>']
    t0,t1=samples[0][0],samples[-1][0]
    for index,(title,cols,labels) in enumerate(panels):
        top=30+index*200
        values=[r[c] for r in samples for c in cols if r[c] is not None]
        lo,hi=(min(values),max(values)) if values else (0,1)
        span=max(hi-lo,1e-30)
        parts.append(f'<text x="12" y="{top}" font-size="15">{title}; {lo:.4g} .. {hi:.4g}</text>')
        for k,c in enumerate(cols):
            parts.append(f'<text x="{650+110*k}" y="{top}" fill="{colors[k]}" font-size="13">{labels[k]}</text>')
            # Separate runs at misses; never connect across an intercepted ray.
            runs=[];current=[]
            for r in samples:
                if r[c] is None:
                    if current:runs.append(current);current=[]
                else:current.append(f'{35+930*(r[0]-t0)/(t1-t0):.2f},{top+160-140*(r[c]-lo)/span:.2f}')
            if current:runs.append(current)
            for run in runs:parts.append(f'<polyline fill="none" stroke="{colors[k]}" stroke-width=".7" points="'+ ' '.join(run)+'"/>')
        parts.append(f'<text x="35" y="{top+180}" font-size="12">Time: {t0:.5g} .. {t1:.5g} s</text>')
    parts.append('</svg>');path.write_text('\n'.join(parts))


def run(trace, selection, output, *, field=None, samples=4096):
    if type(samples) is not int or not 64<=samples<=65536:raise ValueError('invalid raster diagnostic sample count')
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    source,pixels=source_summary(selection)
    phosphor.png(out/'logical-reference.png',source['width'],source['height'],pixels)
    renderer=beam_render.Renderer(field=field,backend='compiled',bundle_budget=samples)
    events=selection['events'];ticks=[e[0] for e in events]
    raster=[];lit=[];native_active=[];reasons=collections.Counter();series=[]
    ranges={n:[math.inf,-math.inf] for n in beam_render.FIELDS[1:]}
    bright=0;active=0
    for row in phase_samples(trace,samples,source['field_s']):
        tick=(row[0]*selection['clock_hz'])%selection['period_ticks']
        video=events[max(0,bisect.bisect_right(ticks,tick)-1)][1]
        bundle=renderer.bundle(row)
        for ray in bundle['rays']:reasons[ray['reason']]+=1
        x=y=None
        if bundle['landed_fraction']:
            x,y=bundle['x_m'],bundle['y_m'];raster.append((x,y))
            if row[-1]>1e-12:lit.append((x,y))
            if video:native_active.append((x,y))
        bright+=row[-1]>1e-12;active+=bool(video)
        for name,value in zip(beam_render.FIELDS[1:],row[1:]):
            ranges[name][0]=min(ranges[name][0],value);ranges[name][1]=max(ranges[name][1],value)
        series.append((row[0],row[1]-row[4],row[2]-row[4],row[3]-row[4],row[4],*row[5:],x,y))
    plot(out/'scan.svg',series)
    report=dict(format='dac-scan-diagnostics-v1',source=source,
        source_content_sha256=selection.get('source_content_sha256'),
        models=beam_render.model_hashes() | {'scan_diagnostics.py':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()},
        trace_sha256=hashlib.sha256(Path(trace).read_bytes()).hexdigest(),
        qualification='sampled-diagnostic-not-acceptance',samples=samples,
        raster_bounds=bounds(raster),illuminated_bounds=bounds(lit),native_active_bounds=bounds(native_active),
        sampled_ranges=ranges,ray_outcomes=dict(reasons),video_high_samples=active,emitting_samples=bright,
        field_parameters=renderer.field,electrode_reference='cathode subtracted exactly once by Renderer.bundle',
        conclusions=[],full_monitor_qualified=False)
    if source['active_lines'] and len(source['active_lines'])<source['height']/4:
        report['conclusions'].append('Native source occupies fewer than one quarter of field lines; illuminated extent cannot establish full raster height.')
    extent=report['raster_bounds']
    if extent and extent['height_m']<renderer.field['screen_height_m']/4:
        report['conclusions'].append('Sampled raster is also vertically undersized under the declared yoke field model, independently of sparse VIDEO.')
    if not bright:report['conclusions'].append('No beam emission detected at diagnostic sample phases; inspect full-bandwidth VIDEO and gun gating before declaring darkness.')
    report['limitations']=['Uniform sampling can miss narrow video pulses and extrema; use the full trace for numerical acceptance.',
                          'Raster includes retrace; it is reported separately from native-active and illuminated extents.',
                          'The logical timing reference is never fed into CRT rendering.']
    (out/'diagnostics.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',type=Path,required=True)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--field-parameters',type=Path)
    a=p.parse_args();r=run(a.trace,steady_supply.select(lab.parse_capture(a.capture)),a.output,
        field=json.loads(a.field_parameters.read_text()) if a.field_parameters else None)
    print(json.dumps(r,indent=2))
