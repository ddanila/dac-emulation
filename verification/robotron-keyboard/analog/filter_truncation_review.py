#!/usr/bin/env python3
"""Retain waveform-preserving full-window controls for filter timestep diagnostics."""
import argparse
import json
import lzma
import re
import shutil
from pathlib import Path
from filter_truncation_log import diagnostic, filter_truncation_record
from startup_truncation_review import analyze as startup_analyze
from reset_release_driver_review import trace_summary, completed, TRACES
from fixture_grid_review import retain_generator
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent
BASELINE = HERE/'reports/dense-anchored-refinement/25'
WINDOW = (138e-6, 138.5e-6)


def analyze(log):
    records = []; floors = {}
    for line in log.splitlines():
        if not line.startswith('FILTER_TRUNC '):
            continue
        if not filter_truncation_record(line) and not re.fullmatch(
                r'FILTER_TRUNC instance time=\S+ name=\S+ state=\d+ before=\S+ proposed=\S+', line):
            raise ValueError('Malformed filter diagnostic')
        raw = dict(item.split('=', 1) for item in line.split()[2:])
        if not WINDOW[0] <= float.fromhex(raw['time']) <= WINDOW[1]:
            raise ValueError('Record outside filter diagnostic window')
        if 'q0' in raw:
            state = raw['state']
            floors.setdefault(state, {'chargeFloorActive': 0, 'storedChargeAboveFloor': 0})
            floor_active = max(abs(float.fromhex(raw[k])) for k in ('q0', 'q1')) <= float.fromhex(raw['chgtol'])
            floors[state]['chargeFloorActive' if floor_active else 'storedChargeAboveFloor'] += 1
        records.append(line.replace('FILTER_TRUNC ', 'STARTUP_TRUNC ', 1))
    result = startup_analyze('\n'.join(records), window=WINDOW)
    for state, counts in floors.items():
        result['states'][state].update(counts)
    result['windowSeconds'] = list(WINDOW)
    result['scope'] = ('Logged candidate timestep reductions in the filter window, including steps later rejected. '
        'Device evaluation order affects counts; reductions do not alone identify accepted steps. '
        'Binary64 and 64-digit arithmetic replay use the same logged histories and cannot measure accumulated '
        'history error or physical accuracy. The charge-floor counts distinguish the absolute floor from stored-charge scaling.')
    return result


def validate_run(run, base, mode, executable_hash):
    if run.get('filterTruncAudit') != (mode == 'enabled') or run['runtime']['executable']['sha256'] != executable_hash:
        raise ValueError('Unexpected instrumentation control')
    ignored = {'elapsedSeconds', 'generatorSha256', 'filterTruncAudit', 'runtime'}
    if {k:v for k,v in run.items() if k not in ignored} != {k:v for k,v in base.items() if k not in ignored}:
        raise ValueError('Changed baseline inputs or numerical settings')
    if {k:v for k,v in run['runtime'].items() if k != 'executable'} != {k:v for k,v in base['runtime'].items() if k != 'executable'}:
        raise ValueError('Changed code models')


def retain(root, build_path, parent_path, out):
    base = json.loads((BASELINE/'run.json').read_text())
    baseline_traces = json.loads((BASELINE/'trace-endpoints.json').read_text())
    build = json.loads(build_path.read_text()); parent = json.loads(parent_path.read_text())
    fixture = json.loads((HERE/'fixtures/filter-truncation/sources.json').read_text())
    if build['base'] != fixture or fixture['baseRuntimeSha256'] != parent['executableSha256']:
        raise ValueError('Unmatched parent runtime')
    if parent['base']['baseRuntimeSha256'] != base['runtime']['executable']['sha256']:
        raise ValueError('Unmatched baseline runtime ancestry')
    if parent['patchSha256'] != sha(HERE/'engine-patches/ngspice-47-startup-truncation-audit.patch'):
        raise ValueError('Changed parent instrumentation')
    for name,digest in fixture['files'].items():
        if sha(HERE/'fixtures/filter-truncation'/Path(name).name) != digest:
            raise ValueError('Changed filter patch base')
    if any(fixture['files'][name] != digest for name,digest in parent['sourceSha256'].items()):
        raise ValueError('Filter patch base differs from parent build')
    if build['patchSha256'] != sha(HERE/'engine-patches/ngspice-47-filter-truncation-audit.patch'):
        raise ValueError('Changed filter instrumentation')
    out.mkdir(parents=True, exist_ok=False)
    runs = {}; cases = {}; logs = {}
    for mode in ('disabled', 'enabled'):
        src = root/('filter-trunc-full-'+mode)
        run = json.loads((src/'run.json').read_text()); runs[mode] = run
        validate_run(run, base, mode, build['executableSha256'])
        for name,digest in {**run['inputs'], 'io.cir':run['deckSha256'], 'sampling-grid.json':run['samplingGridSha256']}.items():
            if sha(src/name) != digest:
                raise ValueError('Changed capture input '+name)
        traces = {name:trace_summary(src/name) for name in TRACES}
        log = (src/'ngspice.log').read_text(); logs[mode] = log
        if not completed(run, traces, diagnostic(log)):
            raise ValueError('Incomplete waveform control')
        if any(t['sha256'] != baseline_traces[name]['sha256'] for name,t in traces.items()):
            raise ValueError('Instrumentation changed a waveform')
        if mode == 'disabled' and 'FILTER_TRUNC ' in log:
            raise ValueError('Disabled logging emitted diagnostics')
        dst = out/mode; dst.mkdir()
        for name in ('run.json', 'io.cir', 'sampling-grid.json'):
            shutil.copyfile(src/name,dst/name)
        with lzma.open(dst/'ngspice.log.xz','wt') as stream:
            stream.write(log)
        (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
        cases[mode] = {'completed':True, 'allFiveWaveformsByteIdenticalToBaseline':True}
    a,b = runs.values()
    ignored = {'elapsedSeconds', 'filterTruncAudit'}
    if {k:v for k,v in a.items() if k not in ignored} != {k:v for k,v in b.items() if k not in ignored}:
        raise ValueError('Audit pair differs beyond logging')
    generator = retain_generator((root/'filter-trunc-runner.py',), out, a['generatorSha256'])
    shutil.copyfile(build_path,out/'build.json'); shutil.copyfile(parent_path,out/'parent-build.json')
    result = {'schema':1, 'cases':cases, 'analysis':analyze(logs['enabled']), 'captureGenerator':generator,
        'baselineAssessmentSha256':sha(BASELINE.parent/'assessment.json'), 'qualified':False,
        'sources':{name:sha(HERE/name) for name in ('filter_truncation_review.py', 'filter_truncation_log.py',
            'startup_truncation_review.py', 'startup_truncation_log.py', 'reset_release_driver_review.py',
            'fixture_grid_review.py', 'engine-patches/ngspice-47-filter-truncation-audit.patch')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runs','build','parent-build','out'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    result=retain(args.runs,args.build,args.parent_build,args.out)
    print(json.dumps({k:{n:v for n,v in s.items() if n != 'worstArithmeticWitness'} for k,s in result['analysis']['states'].items()},indent=2))
