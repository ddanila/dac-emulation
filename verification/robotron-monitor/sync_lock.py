"""Measure flyback phase against recorded ordinary BSYN pulses.

Broad vertical pulses are excluded, not replaced by a nominal line clock.
A constant phase offset is allowed; phase fitting, time warping and gain fitting
are not. A flyback can match at most one source edge.
"""
import bisect
import math


def ordinary_edges(selection):
    events=selection['events'];period=selection['period_ticks']
    line=selection['line_period_ticks'];hz=selection['clock_hz']
    # Include the periodic seam, since a selected field can start in BSYN low.
    rows=[[e[0]+k*period,*e[1:]] for k in (-1,0,1) for e in events if e[0]<period]
    falling=None;edges=[]
    for a,b in zip(rows,rows[1:]):
        if a[2]==1 and b[2]==0:falling=b[0]
        if a[2]==0 and b[2]==1 and falling is not None:
            if 0<=falling<period and 0<b[0]-falling<.3*line:edges.append(falling/hz)
            falling=None
    return edges


def compare(flybacks,selection,start,end):
    line=selection['line_period_ticks']/selection['clock_hz']
    period=selection['period_ticks']/selection['clock_hz']
    if any(not math.isfinite(t) for t in flybacks) or any(b<=a for a,b in zip(flybacks,flybacks[1:])):
        raise ValueError('flybacks must be finite and strictly increasing')
    source=ordinary_edges(selection)
    reference=[k*period+t for k in range(math.floor(start/period)-1,math.ceil(end/period)+1)
               for t in source if start+line<=k*period+t<end-line]
    residual=[];used=set();missing=0;duplicate=0;matched=[]
    for t in reference:
        i=bisect.bisect_left(flybacks,t)
        candidates=[j for j in (i-1,i) if 0<=j<len(flybacks)]
        if not candidates:missing+=1;continue
        j=min(candidates,key=lambda j:abs(flybacks[j]-t))
        if abs(flybacks[j]-t)>.5*line:missing+=1;continue
        if j in used:duplicate+=1
        used.add(j);residual.append((flybacks[j]-t)/line);matched.append((t,flybacks[j]-t))
    # Wrap only the constant phase offset. Unwrap residuals relative to it;
    # a cycle slip still fails the range/count checks, never an accumulated fit.
    offset=math.atan2(sum(math.sin(2*math.pi*r) for r in residual),
                      sum(math.cos(2*math.pi*r) for r in residual))/(2*math.pi) if residual else None
    aligned=[(r-offset+.5)%1-.5 for r in residual] if residual else []
    variation=max(aligned)-min(aligned) if aligned else None
    adjacent=[abs(b[1]-a[1]) for a,b in zip(matched,matched[1:])
              if .99*line<=b[0]-a[0]<=1.01*line]
    jitter=max(adjacent) if adjacent else None
    in_window=[i for i,t in enumerate(flybacks) if reference and reference[0]-.5*line<=t<=reference[-1]+.5*line]
    unmatched=len(set(in_window)-used)
    field_count=(end-start)/period
    fields=round(field_count) if abs(field_count-round(field_count))<1e-6 else None
    return dict(accepted=bool(reference) and missing==0 and duplicate==0 and unmatched==0 and variation is not None and variation<=.01,
                reference='captured ordinary active-low BSYN edges',reference_edges=len(reference),
                matched_edges=len(residual),missing_edges=missing,reused_flybacks=duplicate,
                flybacks_in_window=len(in_window),unmatched_flybacks=unmatched,
                fields=fields,
                constant_phase_offset_lines=offset,phase_variation_lines=variation,threshold_lines=.01,
                maximum_adjacent_jitter_s=jitter,adjacent_pairs=len(adjacent),
                adjacent_jitter_limit_s=36e-9,
                adjacent_jitter_accepted=jitter is not None and jitter<=36e-9,
                vertical_sync_edges_excluded=True)
