"""Measure synthetic-grid size from circuit waveforms and central CRT rays.

Markers are the centers of VIDEO intervals in the selected grid capture. The
ray solver receives interpolated electrode voltages and both yoke currents;
no framebuffer coordinate is supplied to the circuit or to the ray solver.
"""
import math
import statistics

import steady_supply
import trajectory_native


def marker_times(selection, clock_hz, start_s):
    line=selection['line_period_ticks'];period=selection['period_ticks']
    if period%line or not math.isfinite(clock_hz) or clock_hz<=0:
        raise ValueError('invalid grid timing')
    rows=[[] for _ in range(period//line)]
    for a,b in zip(selection['events'],selection['events'][1:]+[[period,0,0,0]]):
        if not a[1]:continue
        lo=a[0]
        while lo<b[0]:
            n=lo//line;hi=min(b[0],(n+1)*line)
            rows[n].append((lo-n*line,hi-n*line))
            lo=hi
    active=[i for i,row in enumerate(rows) if row]
    if len(active)<.9*len(rows):raise ValueError('grid does not cover the active screen')
    stripe=[i for i,row in enumerate(rows) if len(row)>=5]
    full=[i for i,row in enumerate(rows) if len(row)==1 and rows[i][0][1]-rows[i][0][0]>.5*line]
    if len(stripe)<5 or len(full)<5:raise ValueError('grid lacks measured vertical or horizontal markers')
    chosen=sorted(stripe,key=lambda i:abs(i-(active[0]+active[-1])/2))[:5]
    groups=[]
    for n in full:
        if not groups or n>groups[-1][-1]+1:groups.append([n])
        else:groups[-1].append(n)
    if len(groups)<5:raise ValueError('grid lacks separated horizontal marker rows')
    targets=[]
    for n in chosen:
        for j,(a,b) in enumerate(rows[n]):
            targets.append((start_s+(n*line+(a+b)/2)/clock_hz,('stripe',n,j)))
    for j,group in enumerate(groups):
        n=group[len(group)//2];a,b=rows[n][0]
        targets.append((start_s+(n*line+(a+b)/2)/clock_hz,('horizontal',j,0)))
    return sorted(targets),sorted(chosen),len(groups)


def _interpolate(trace, targets, start_s, end_s):
    previous=None;index=0;result={};first=last=None
    probes=('v(eht)','v(g2)','v(g4)','v(cathode)','i(lhorizontal)','i(lvertical)',
            'v(xcrt.launch_current_ua)')
    threshold_ua=.01;peak_ua=0.;emitting_s=0.
    for row in steady_supply.raw_rows(trace):
        t=row['time']
        if first is None:first=t
        last=t
        if any(name not in row for name in probes):
            raise ValueError('grid geometry trace lacks an electrode or yoke probe')
        if previous is not None:
            a=max(previous['time'],start_s);b=min(t,end_s)
            if b>a:
                va=previous['v(xcrt.launch_current_ua)']+(row['v(xcrt.launch_current_ua)']-previous['v(xcrt.launch_current_ua)'])*(a-previous['time'])/(t-previous['time'])
                vb=previous['v(xcrt.launch_current_ua)']+(row['v(xcrt.launch_current_ua)']-previous['v(xcrt.launch_current_ua)'])*(b-previous['time'])/(t-previous['time'])
                peak_ua=max(peak_ua,va,vb)
                if va>threshold_ua and vb>threshold_ua:emitting_s+=b-a
                elif (va>threshold_ua)!=(vb>threshold_ua):
                    crossing=a+(b-a)*(threshold_ua-va)/(vb-va)
                    emitting_s+=(crossing-a if va>threshold_ua else b-crossing)
            while index<len(targets) and targets[index][0]<=t:
                target,key=targets[index]
                if target<previous['time']:raise ValueError('grid marker is outside electrical trace')
                f=(target-previous['time'])/(t-previous['time'])
                result[key]={name:previous[name]+f*(row[name]-previous[name]) for name in probes}
                index+=1
        previous=row
    if first is None or abs(first)>1e-12 or not math.isclose(last,end_s,rel_tol=0,abs_tol=1e-9) or index!=len(targets):
        raise ValueError('grid geometry trace does not span the completed field')
    fraction=emitting_s/(end_s-start_s)
    lit_markers=sum(row['v(xcrt.launch_current_ua)']>threshold_ua for row in result.values())
    marker_fraction=lit_markers/len(targets)
    if peak_ua<.05 or fraction<.005 or marker_fraction<.1:
        raise ValueError('grid geometry has no sustained modeled beam launch')
    return result,dict(beam_launch_peak_ua=peak_ua,
                       beam_launch_emitting_fraction=fraction,
                       beam_launch_marker_fraction=marker_fraction,
                       beam_launch_threshold_ua=threshold_ua)


def _spacing_error(values):
    differences=[b-a for a,b in zip(values,values[1:])]
    if not differences or not all(math.isfinite(v) and abs(v)>1e-6 for v in differences):
        raise ValueError('grid markers do not have distinct screen positions')
    if min(differences)<0<max(differences):
        raise ValueError('grid marker order reverses on screen')
    lengths=list(map(abs,differences));mean=statistics.mean(lengths)
    return max(abs(v/mean-1) for v in lengths)


def measure(trace, selection, clock_hz, *, start_s, end_s, field, ray_solver=None):
    period=selection['period_ticks']/clock_hz
    if not math.isclose(end_s-start_s,period,rel_tol=0,abs_tol=1e-9):
        raise ValueError('geometry measurement must cover one full grid field')
    targets,stripe_rows,horizontal_count=marker_times(selection,clock_hz,start_s)
    samples,emission=_interpolate(trace,targets,start_s,end_s)
    if ray_solver is None:ray_solver=trajectory_native.Backend().ray
    positions={}
    for _,key in targets:
        row=samples[key];cathode=row['v(cathode)']
        ray=ray_solver(row['v(eht)']-cathode,row['v(g2)']-cathode,
                       row['v(g4)']-cathode,row['i(lhorizontal)'],row['i(lvertical)'],
                       overrides=field)
        if not ray.get('landed') or not all(math.isfinite(ray.get(k,float('nan'))) for k in ('x_m','y_m')):
            raise ValueError('grid border trajectory does not land on screen')
        positions[key]=(ray['x_m'],ray['y_m'])
    widths=[];horizontal_errors=[];centers=[]
    for n in stripe_rows:
        xs=[positions[('stripe',n,j)][0] for j in range(len([key for key in positions if key[:2]==('stripe',n)]))]
        horizontal_errors.append(_spacing_error(xs))
        widths.append(abs(xs[-1]-xs[0]));centers.append((xs[-1]+xs[0])/2)
    ys=[positions[('horizontal',j,0)][1] for j in range(horizontal_count)]
    vertical_error=_spacing_error(ys)
    width=statistics.median(widths);height=abs(ys[-1]-ys[0])
    if width<=0 or height<=0:raise ValueError('grid has zero picture extent')
    return dict(picture_width_mm=width*1000,picture_height_mm=height*1000,
                horizontal_linearity=max(horizontal_errors),vertical_linearity=vertical_error,
                horizontal_center_mm=statistics.median(centers)*1000,
                vertical_center_mm=(ys[0]+ys[-1])*500,
                stripe_rows=len(stripe_rows),horizontal_marker_rows=horizontal_count,
                marker_count=len(targets),
                **emission,
                method='source-grid-markers-through-connected-electrodes-yoke-and-central-ray')
