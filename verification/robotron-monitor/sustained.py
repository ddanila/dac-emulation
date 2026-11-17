"""Capture selection and stability gates, never a substitute for a connected solver."""
import bisect
import hashlib
import json
import math
import frames

FIELDS=16
SETTLE_FIELDS=8


def select(capture, *, tau_s=.025):
    if not math.isfinite(tau_s) or not 1e-6<=tau_s<=10:raise ValueError('invalid phosphor decay')
    result=frames.analyze(capture,fields=1,pre_roll_fields=0)
    result.update(fields_requested=FIELDS,selection=None,status='incomplete',
                  source_content_verified=False,phosphor_preroll_min_s=7*tau_s)
    period=result.get('field_period_ticks');hz=capture['clock_hz']
    if period is None:return result
    preroll=max(SETTLE_FIELDS,math.ceil(7*tau_s*hz/period))
    result['pre_roll_fields_requested']=preroll
    events=capture['events'];ticks=[e[0] for e in events]
    complete=result['complete_fields']
    for field in complete:
        start,end=field['start_tick'],field['end_tick']
        i=bisect.bisect_right(ticks,start)-1
        normalized=[[0,*events[i][1:]]]
        for event in events[i+1:bisect.bisect_left(ticks,end)]:
            if event[1:]!=normalized[-1][1:]:normalized.append([event[0]-start,*event[1:]])
        field['content_sha256']=hashlib.sha256(json.dumps([end-start,normalized],separators=(',',':')).encode()).hexdigest()
    for i in range(preroll,len(complete)-FIELDS+1):
        pre=complete[i-preroll:i];selected=complete[i:i+FIELDS]
        if not all(f['usable'] for f in pre+selected):continue
        if len({f['content_sha256'] for f in selected})!=1:continue
        if (selected[0]['start_tick']-pre[0]['start_tick'])/hz<7*tau_s:continue
        result.update(status='complete',reason=None,source_content_verified=True,
                      source_content_sha256=selected[0]['content_sha256'],
                      selection=dict(simulate_from_tick=0,render_start_tick=selected[0]['start_tick'],
                                     render_end_tick=selected[-1]['end_tick'],
                                     frame_ticks=[f['end_tick'] for f in selected]))
        return result
    result['reason']='No 16 unchanged complete fields following sufficient original optical/electrical pre-roll.'
    return result


def assess(records, *, phosphor_preroll_s, tau_s=.025):
    """Assess 8 settling + 16 exported field summaries from a continuous run.

    Metrics are field averages or phase-aligned measurements, all positive
    magnitudes. This gate does not assert solver provenance, model accuracy,
    equilibrium, numerical refinement, or specimen qualification.
    """
    required={'p41_v','p22_v','n16_magnitude_v','eht_v','width_m','height_m','brightness_w_m2'}
    report=dict(format='dac-crt-sustained-stability-v1',accepted=False,full_monitor_qualified=False,
                fields_required=FIELDS,settle_fields_required=SETTLE_FIELDS,failures=[],variation={})
    if not all(math.isfinite(v) and v>=0 for v in (phosphor_preroll_s,tau_s)) or tau_s<=0:
        raise ValueError('invalid optical pre-roll')
    if phosphor_preroll_s<7*tau_s:report['failures'].append('insufficient phosphor pre-roll')
    if len(records)!=FIELDS+SETTLE_FIELDS:
        report['failures'].append('expected eight settling and sixteen output fields');return report
    previous=None;periods=[]
    for record in records:
        start,end=record['start_s'],record['end_s']
        if not math.isfinite(start) or not math.isfinite(end) or not 0<=start<end:
            raise ValueError('invalid field interval')
        if previous is not None and start!=previous:report['failures'].append('noncontinuous field intervals')
        previous=end;periods.append(end-start)
        if record.get('locked') is not True:report['failures'].append('synchronization not locked')
        metrics=record['metrics']
        if set(metrics)!=required or any(not math.isfinite(v) or v<=0 for v in metrics.values()):
            raise ValueError('invalid sustained field metrics')
        if not math.isfinite(record['phase_error_lines']) or abs(record['phase_error_lines'])>=.01:
            report['failures'].append('horizontal phase instability')
    if len({r['source_content_sha256'] for r in records[-FIELDS:]})!=1:
        report['failures'].append('source content changed')
    for key in sorted(required):
        values=[r['metrics'][key] for r in records]
        variation=(max(values)-min(values))/(sum(values)/len(values))
        report['variation'][key]=variation
        if variation>=.01:report['failures'].append('unstable '+key)
    if (max(periods)-min(periods))/(sum(periods)/len(periods))>=.01:
        report['failures'].append('field period instability')
    report['failures']=sorted(set(report['failures']))
    report['accepted']=not report['failures']
    return report
