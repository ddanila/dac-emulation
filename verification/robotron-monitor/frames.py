#!/usr/bin/env python3
"""Identify complete fields in recorded BSYN; never synthesize or repeat video.

The detector is specific to the 1715W E05/E07 connector contract. Broad active-low
pulses identify vertical sync. It is observation metadata, NOT monitor sync lock.
All times remain integer capture ticks; the input and its pre-roll are preserved.
"""
import argparse,hashlib,json,statistics
from pathlib import Path
import lab


def analyze(capture, *, fields=1, pre_roll_fields=1):
    if capture.get('format')!='dac-monitor-input-v2':
        raise ValueError('complete-field selection requires v2 VIDEO/BSYN/INTENS')
    if type(fields) is not int or not 1<=fields<=16 or type(pre_roll_fields) is not int or not 0<=pre_roll_fields<=16:
        raise ValueError('invalid field selection budget')
    events=capture['events'];hz=capture['clock_hz'];pulses=[];start=None
    # Initial low may be a truncated pulse; do not count it as a boundary.
    for a,b in zip(events,events[1:]):
        if a[2]==1 and b[2]==0:start=b[0]
        elif a[2]==0 and b[2]==1:
            if start is not None:pulses.append((start,b[0]))
            start=None
    result=dict(format='dac-monitor-fields-v1',status='incomplete',clock_hz=hz,
                capture_end_tick=events[-1][0],fields_requested=fields,
                pre_roll_fields_requested=pre_roll_fields,field_boundaries=[],
                complete_fields=[],selection=None,monitor_lock_verified=False,
                input_repeated=False)
    if len(pulses)<12:
        result['reason']='Insufficient complete BSYN pulses; capture may be short or raster stopped.'
        return result
    periods=[b[0]-a[0] for a,b in zip(pulses,pulses[1:])]
    line=round(statistics.median(periods));result['line_period_ticks']=line
    if not 20e-6<=line/hz<=150e-6:
        result['reason']='BSYN line period outside the supported connector observation range.'
        return result
    broad=[p for p in pulses if line*.5 < p[1]-p[0] < line*1.1]
    groups=[]
    for p in broad:
        if not groups or p[0]-groups[-1][-1][0]>line*1.5:groups.append([])
        groups[-1].append(p)
    # Require an observed ordinary line pulse before and after each group, so a
    # capture beginning or ending inside vertical sync cannot acquire a boundary.
    narrow=[p for p in pulses if 0 < p[1]-p[0] < line*.3]
    boundaries=[]
    for group in groups:
        if not 2<=len(group)<=8:continue
        before=[p for p in narrow if 0<group[0][0]-p[0]<line*2.5]
        after=[p for p in narrow if 0<p[0]-group[-1][0]<line*2.5]
        if before and after:boundaries.append(group[0][0])
    result['field_boundaries']=boundaries
    durations=[b-a for a,b in zip(boundaries,boundaries[1:])]
    nominal_field=statistics.median(durations) if durations else None
    result['field_period_ticks']=nominal_field
    for a,b in zip(boundaries,boundaries[1:]):
        pp=[p for p in pulses if a<=p[0]<b]
        gaps=[y[0]-x[0] for x,y in zip(pp,pp[1:])]
        # Vertical-entry phase shifts are legal; absent line clocks are not.
        reason=None
        if not .005<=(b-a)/hz<=.1:reason='unsupported field duration'
        elif len(durations)>1 and abs(b-a-nominal_field)>line:
            reason='field period changed or a vertical sync boundary is missing'
        elif (not gaps or max(gaps)>line*2.1 or any(
                y[0]-x[0]>line*1.1 for x,y in zip(pp,pp[1:])
                if x[1]-x[0]<line*.3 and y[1]-y[0]<line*.3)):
            reason='missing line sync inside field'
        result['complete_fields'].append(dict(start_tick=a,end_tick=b,
            duration_ticks=b-a,usable=reason is None,reason=reason))
    chosen=result['complete_fields'][pre_roll_fields:pre_roll_fields+fields]
    preroll=result['complete_fields'][:pre_roll_fields]
    if len(chosen)!=fields or len(preroll)!=pre_roll_fields:
        result['reason']='Capture does not contain enough complete fields and pre-roll.'
    elif any(not f['usable'] for f in preroll+chosen):
        result['reason']='Sync discontinuity in requested pre-roll or frame window.'
    else:
        result.update(status='complete',selection=dict(simulate_from_tick=0,
            render_start_tick=chosen[0]['start_tick'],render_end_tick=chosen[-1]['end_tick'],
            frame_ticks=[f['end_tick'] for f in chosen]))
    return result


def prepare(path,output,*,fields=1,pre_roll_fields=1):
    path=Path(path);output=Path(output);output.mkdir(parents=True,exist_ok=False)
    data=lab.parse_capture(path);raw=path.read_bytes()
    # Parse the archived bytes too: refuse a changing input rather than hashing
    # a different capture from the one whose boundaries were selected.
    (output/'input.json').write_bytes(raw)
    if data!=lab.parse_capture(output/'input.json'):raise ValueError('capture changed during import')
    result=analyze(data,fields=fields,pre_roll_fields=pre_roll_fields)
    result['capture_sha256']=hashlib.sha256(raw).hexdigest()
    result['qualification']=data['qualification']
    result['input_sha256']=data.get('input_sha256',{})
    (output/'fields.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--fields',type=int,default=1);p.add_argument('--pre-roll-fields',type=int,default=1)
    a=p.parse_args();r=prepare(a.capture,a.output,fields=a.fields,pre_roll_fields=a.pre_roll_fields)
    print(json.dumps(r,indent=2));raise SystemExit(0 if r['status']=='complete' else 2)
