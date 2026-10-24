#!/usr/bin/env python3
"""Retain complete bridge timing controls and recheck their logged interpretation."""
import argparse
import json
import lzma
from pathlib import Path
import shutil
from bridge_rollback_log import analyze
from live_bridge_time_review import review
from trace_io import open_binary, open_text
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent


def check(out):
    expected = json.loads((out/'manifest.json').read_text())
    actual = {str(p.relative_to(out)): sha(p) for p in out.rglob('*')
              if p.is_file() and p.name != 'manifest.json'}
    if actual != expected:
        raise ValueError('Changed retained bridge evidence')
    assessment = json.loads((out/'assessment.json').read_text())
    end = next(iter(assessment['comparisons'].values()))['lastSeconds']
    with open_text(out/'ngspice.log') as stream:
        timing = analyze(stream, expected_end=end)
    if timing != assessment['timing']:
        raise ValueError('Changed bridge timing interpretation')


def retain(capture, control, baseline, base_bridge, build, out):
    result = review(capture, control, baseline, base_bridge, build)
    out.mkdir(parents=True, exist_ok=False)
    for name in ('run.json', 'bridge.json', 'io.cir', 'capture-generator.py'):
        shutil.copyfile(capture/name, out/name)
    for source, name in ((control/'run.json', 'control.json'),
                         (base_bridge, 'base-bridge.json'),
                         (build, 'build.json')):
        shutil.copyfile(source, out/name)
    if json.loads((baseline/'run.json').read_text()).get('rawOutput'):
        (out/'baseline-traces.json').write_text(json.dumps(result['comparisons'], indent=2)+'\n')
    else:
        shutil.copyfile(baseline/'completion-check.json', out/'baseline-traces.json')
    bridge = json.loads((capture/'bridge.json').read_text())
    vpi_source = Path(bridge['libraries']['vpi']['path']).parent/'vpi.c'
    if sha(vpi_source) != bridge['audit']['sourceSha256']:
        raise ValueError('Changed bridge logger source')
    shutil.copyfile(vpi_source, out/'vpi.c')
    with open_binary(capture/'ngspice.log') as source, lzma.open(out/'ngspice.log.xz', 'wb') as dest:
        shutil.copyfileobj(source, dest, 1024*1024)
    result['retention'] = {
        'fullCapture': str(capture.resolve()),
        'scope': 'Complete raw waveforms remain local, pinned by the run receipt; every sample was compared before retention.',
        'sources': {n: sha(HERE/n) for n in (
            'live_bridge_time_review.py', 'bridge_rollback_log.py',
            'live_bridge_time_capture.py', 'retain_bridge_rollback.py',
            'rollback_dispatch_review.py', 'raw_pair_review.py', 'raw_waveform.py')}}
    (out/'assessment.json').write_text(json.dumps(result, indent=2)+'\n')
    manifest = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    check(out)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('capture', 'control', 'baseline', 'base-bridge', 'build'):
        p.add_argument('--'+name, type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    if a.check:
        check(a.out)
    else:
        if not all((a.capture, a.control, a.baseline, a.base_bridge, a.build)):
            p.error('Retention requires complete capture, control, baseline and build provenance')
        retain(a.capture, a.control, a.baseline, a.base_bridge, a.build, a.out)
