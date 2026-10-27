"""Validate retained local brackets against the complete refinement assessment."""
import json,math
from pathlib import Path
from ttl7406_probe import sha


def review(root):
    r=json.loads((root/'assessment.json').read_text());w=json.loads((root/'maxima.json').read_text());archives=json.loads((root/'retention.json').read_text())['archives']
    if w['assessmentSha256']!=sha(root/'assessment.json'):raise ValueError('Changed witness assessment')
    expected={pair+':'+name for pair in ('coarseFine','fineFinest') for name in r['voltageGate']['failures']}
    if set(w['witnesses'])!=expected:raise ValueError('Incomplete maxima witnesses')
    for label in ('coarse','fine','finest'):
        if w['archives'][label]!={k:archives[label+'/waveform.raw.xz'][k] for k in ('bytes','sha256')}:raise ValueError('Changed witness archive identity')
    widths=[]
    for key,record in w['witnesses'].items():
        pair,name=key.split(':',1);reported=r['comparisons'][pair]['signals'][name];values=[]
        for side in ('left','right'):
            p=record[side];a,b=p['before'],p['after'];t=p['timeSeconds']
            if len(a)!=2 or len(b)!=2 or not all(math.isfinite(v) for v in [*a,*b,t]) or not a[0]<=t<=b[0] or b[0]<=a[0] or t!=reported['timeSeconds']:raise ValueError('Invalid maximum bracket')
            fraction=(t-a[0])/(b[0]-a[0]);value=a[1]+fraction*(b[1]-a[1])
            if fraction!=p['fraction'] or value!=p['interpolatedValue']:raise ValueError('Changed witness interpolation')
            values.append(value);widths.append((b[0]-a[0])*1e12)
        if abs(values[0]-values[1])!=record['absoluteDifference'] or record['absoluteDifference']!=reported['maximumAbsoluteDifference']:raise ValueError('Witness does not reproduce maximum')
    return dict(qualified=False,witnesses=len(expected),allReportedMaximaExactlyReproduced=True,minimumBracketPS=min(widths),maximumBracketPS=max(widths),scope='Arithmetic/identity check of retained local sample brackets. Global maxima are established by the separate complete diagnostic; causes, convergence and general applicability are not established by these witnesses.')
