#!/usr/bin/env python3
"""Check source-bound output clamp witnesses without changing convergence policy."""
import argparse
import json
from pathlib import Path
from ttl7406_probe import sha
import postreset_tick_events as events
import postreset_tick_peaks as peaks
HERE = Path(__file__).resolve().parent
LOCAL = HERE/'reports/postreset-drain-localization'
REFINEMENTS = HERE/'reports/postreset-drain-refinements'


def review(root, local=LOCAL, refinements=REFINEMENTS):
    build = json.loads((root/'candidate-build.json').read_text())
    expected = json.loads((refinements/'coarse/candidate-build.json').read_text())
    if build != expected or sha(root/'vpi.c') != build['outputs']['vpi.c']:
        raise ValueError('Changed candidate source binding')
    source = (root/'vpi.c').read_text()
    clamp = '''        ctx->cosim_context->vtime = get_time(ctx);
        if (ctx->cosim_context->vtime < ctx->base_time)
            ctx->cosim_context->vtime = ctx->base_time;'''
    if source.count(clamp) != 1:
        raise ValueError('Changed output clamp')
    for folder in (local, refinements):
        manifest = json.loads((folder/'manifest.json').read_text())
        if any(sha(folder/name) != digest for name, digest in manifest['files'].items()):
            raise ValueError('Changed retained evidence')
    event_review = events.review(local/'events')
    peak_review = peaks.review(local/'peaks')
    if event_review['fullAssessmentSha256'] != sha(refinements/'assessment.json') or peak_review['fullAssessmentSha256'] != sha(refinements/'assessment.json'):
        raise ValueError('Different full assessments')
    witnesses = []
    for peak in peak_review['peaks']:
        if not peak['node'].startswith('v(n_d'):
            continue
        context = next(c for c in event_review['peakContexts'] if c['peakSeconds'] == peak['timeSeconds'])
        sides = {}
        left, right = peaks.PAIRS[peak['pair']]
        for label in (left, right):
            group = context['events'][label]
            if len(group) != 4 or group[0]['port'] != 'bus_high' or sorted(e['port'] for e in group) != ['bus_high','bus_high','bus_low','bus_low'] or [e['ordinal'] for e in group] != list(range(group[0]['ordinal'],group[0]['ordinal']+4)):
                raise ValueError('Ambiguous bus event neighborhood')
            first = group[0]
            if any(e['actual'] != first['actual'] or e['base'] != first['base'] for e in group):
                raise ValueError('Mixed bus event times')
            effective = max(float(first['actual']), float(first['base']))
            if any(float(e['target']) != effective for e in group[1:]):
                raise ValueError('Following callbacks do not witness clamp result')
            sides[label] = dict(firstOrdinal=first['ordinal'], actualSeconds=float(first['actual']),
                                baseSeconds=float(first['base']), observedFollowingTargetSeconds=effective,
                                clampOffsetSeconds=effective-float(first['actual']))
        offset = sides[right]['observedFollowingTargetSeconds']-sides[left]['observedFollowingTargetSeconds']
        witnesses.append(dict(pair=peak['pair'], node=peak['node'], peakSeconds=peak['timeSeconds'],
                              sides=sides, deliveryOffsetSeconds=offset,
                              crossingMinusDeliverySeconds={k:v-offset for k,v in peak['matchedCrossingDifferenceSeconds'].items()}))
    return dict(qualified=False, convergenceEstablished=False, witnesses=witnesses,
                maximumAbsoluteCrossingResidualSeconds=max(abs(v) for w in witnesses for v in w['crossingMinusDeliverySeconds'].values()),
                inputs={name:sha(path) for name,path in [('vpi.c',root/'vpi.c'),('candidate-build.json',root/'candidate-build.json'),('localizationManifest',local/'manifest.json'),('refinementManifest',refinements/'manifest.json')]},
                scope='Pinned source clamp arithmetic matches subsequent logged callback targets in each selected bus group. Crossing offsets remain measured on absolute-time linear excerpts. No logged stop-callback handle, output values, or input-threshold history: causal sufficiency, scheduler quiescence and a safe correction remain unproven. WR is excluded because its peak windows contain no threshold crossing.')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--check',action='store_true')
    a=p.parse_args(); result=review(a.root); output=a.root/'assessment.json'
    if a.check:
        if result != json.loads(output.read_text()): raise ValueError('Changed clamp assessment')
    else: output.write_text(json.dumps(result,indent=2)+'\n')
