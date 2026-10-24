#!/usr/bin/env python3
"""Replay logged timestep reductions after verifying waveform-preserving controls."""
import argparse
import json
import lzma
import math
import re
import shutil
from decimal import Decimal, localcontext
from pathlib import Path
from compare_firmware_io import sha
from reset_release_driver_review import trace_summary, TRACES
from live_transition_review import diagnostic
from failure_evidence import startup_truncation_record

HERE = Path(__file__).resolve().parent
BASELINE = HERE/'reports/startup-tight-tolerance/25'


def difference(values, deltas, order, exact=False):
    if order not in (1, 2) or len(values) < order+2 or len(deltas) < order+1:
        raise ValueError('Unsupported history shape')
    if not all(math.isfinite(v) for v in values+deltas) or any(d <= 0 for d in deltas):
        raise ValueError('Invalid history values')
    with localcontext() as context:
        context.prec = 64
        convert = Decimal.from_float if exact else float
        diff = list(map(convert, values[:order+2]))
        original = list(map(convert, deltas[:order+1]))
        spans = list(original)
        # Preserve CKTterr's actual in-place denominator recurrence.
        for count in range(order+1, 0, -1):
            for i in range(count):
                diff[i] = (diff[i]-diff[i+1])/spans[i]
            for i in range(count-1):
                spans[i] = spans[i+1] + original[i]
        return diff[0]


def analyze(text):
    states = {}; names = {}; records = 0
    for match in re.finditer(r'STARTUP_TRUNC (error|instance) ([^\r\n]+)', text):
        kind, fields = match.groups()
        raw = dict(item.split('=', 1) for item in fields.split())
        state = int(raw['state'])
        if kind == 'instance':
            if state in names and names[state] != raw['name']:
                raise ValueError('Ambiguous state identity')
            names[state] = raw['name']
            continue
        r = {k: int(v) if k in ('state', 'order') else float.fromhex(v) for k,v in raw.items()}
        if not all(math.isfinite(v) for v in r.values()) or not .75e-6 <= r['time'] <= 1.05e-6 or r['proposed'] >= r['before']:
            raise ValueError('Invalid reduction or audit window')
        values = [r['q'+str(i)] for i in range(4)]
        deltas = [r['dt'+str(i)] for i in range(3)]
        reproduced = difference(values, deltas, r['order'])
        if reproduced != r['difference']:
            raise ValueError('Binary64 replay differs from logged arithmetic')
        exact = difference(values, deltas, r['order'], True)
        with localcontext() as context:
            context.prec = 64
            error = abs(Decimal.from_float(reproduced)-exact)
            relative = error/abs(exact) if exact else None
        summary = states.setdefault(state, {'reductions': 0, 'chargeToleranceDominant': 0,
            'currentToleranceDominant': 0, 'maximumRelativeArithmeticError': None, 'worstArithmeticWitness': None})
        summary['reductions'] += 1
        summary['chargeToleranceDominant'] += r['chargetol'] >= r['currenttol']
        summary['currentToleranceDominant'] += r['currenttol'] > r['chargetol']
        if relative is not None and (summary['maximumRelativeArithmeticError'] is None or relative > Decimal(summary['maximumRelativeArithmeticError'])):
            summary['maximumRelativeArithmeticError'] = str(relative)
            summary['worstArithmeticWitness'] = {'logged': raw, 'exactRecurrence': str(exact), 'absoluteArithmeticError': str(error)}
        records += 1
    if not records:
        raise ValueError('No startup truncation records')
    for state, summary in states.items():
        summary['instance'] = names.get(state)
    return {'records': records, 'binary64ReplayExact': True,
        'states': {str(k):v for k,v in sorted(states.items())},
        'scope': 'Logged reductions in 0.75–1.05 us, including candidate steps that may later be rejected. Counts follow device evaluation order and do not alone identify the final accepted step. The 64-digit replay preserves the kernel denominator recurrence on the same binary64 charge/flux histories; it cannot measure error already present in those histories or physical accuracy. Unmapped state identities remain null.'}


def retain(root, build_path, out):
    out.mkdir(parents=True, exist_ok=False)
    base = json.loads((BASELINE/'run.json').read_text())
    baseline_traces = json.loads((BASELINE/'trace-endpoints.json').read_text())
    build = json.loads(build_path.read_text())
    if build['base'] != json.loads((HERE/'fixtures/startup-truncation/sources.json').read_text()) or build['base']['baseRuntimeSha256'] != base['runtime']['executable']['sha256']:
        raise ValueError('Unmatched source runtime')
    if build['patchSha256'] != sha(HERE/'engine-patches/ngspice-47-startup-truncation-audit.patch'):
        raise ValueError('Changed instrumentation patch')
    runs = {}; cases = {}; logs = {}
    for mode in ('disabled', 'enabled'):
        src = root/('startup-trunc-v2-'+mode)
        run = json.loads((src/'run.json').read_text()); runs[mode] = run
        if run['startupTruncAudit'] != (mode == 'enabled') or run['exitCode'] != 0 or run['timedOut']:
            raise ValueError('Failed or unexpected audit control')
        if run['solverDiagnostic'] and not (mode == 'enabled' and startup_truncation_record(run['solverDiagnostic'])):
            raise ValueError('Failed or unexpected audit control')
        if run['runtime']['executable']['sha256'] != build['executableSha256']:
            raise ValueError('Different instrumented runtime')
        ignored = {'elapsedSeconds', 'generatorSha256', 'startupTruncAudit', 'runtime', 'solverDiagnostic'}
        if {k:v for k,v in run.items() if k not in ignored} != {k:v for k,v in base.items() if k not in ignored}:
            raise ValueError('Changed inputs or numerical settings')
        if {k:v for k,v in run['runtime'].items() if k != 'executable'} != {k:v for k,v in base['runtime'].items() if k != 'executable'}:
            raise ValueError('Changed code models')
        for name,digest in {**run['inputs'], 'io.cir':run['deckSha256'], 'sampling-grid.json':run['samplingGridSha256']}.items():
            if sha(src/name) != digest:
                raise ValueError('Changed input '+name)
        traces = {n:trace_summary(src/n) for n in TRACES}
        if any(t['sha256'] != baseline_traces[n]['sha256'] for n,t in traces.items()):
            raise ValueError('Instrumentation changed a waveform')
        log = (src/'ngspice.log').read_text(); logs[mode] = log
        if diagnostic(log) or 'condition met: stop' not in log:
            raise ValueError('Unclean diagnostic halt')
        if mode == 'disabled' and 'STARTUP_TRUNC ' in log:
            raise ValueError('Disabled logging emitted diagnostics')
        dst = out/mode; dst.mkdir()
        for name in ('run.json', 'io.cir', 'sampling-grid.json'):
            shutil.copyfile(src/name,dst/name)
        with lzma.open(dst/'ngspice.log.xz','wt') as f:
            f.write(log)
        (dst/'trace-endpoints.json').write_text(json.dumps(traces,indent=2)+'\n')
        cases[mode] = {'allFiveWaveformsByteIdenticalToBaseline':True, 'originalDiagnosticReclassified':bool(run['solverDiagnostic'])}
    a,b = runs.values()
    if {k:v for k,v in a.items() if k not in ('elapsedSeconds','startupTruncAudit','solverDiagnostic')} != {k:v for k,v in b.items() if k not in ('elapsedSeconds','startupTruncAudit','solverDiagnostic')}:
        raise ValueError('Audit pair differs beyond logging')
    failed = root/'startup-trunc-enabled-disk-full'
    dst = out/'failed-disk-full'; dst.mkdir()
    for name in ('failure.json', 'build.json', 'instrumentation.patch', 'io.cir', 'sampling-grid.json', 'ngspice.log.gz'):
        shutil.copyfile(failed/name, dst/name)
    shutil.copyfile(build_path,out/'build.json')
    result = {'schema':1, 'cases':cases, 'failedAttempt': {'path':'failed-disk-full', 'countsForQualification':False}, 'analysis':analyze(logs['enabled']),
        'baselineAssessmentSha256':sha(BASELINE.parent/'assessment.json'), 'qualified':False,
        'sources':{n:sha(HERE/n) for n in ('startup_truncation_review.py', 'live_transition_probe.py',
            'engine-patches/ngspice-47-startup-truncation-audit.patch', 'failure_evidence.py')}}
    (out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n')
    (out/'manifest.json').write_text(json.dumps({str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.is_file()},indent=2)+'\n')
    print(json.dumps({k:{n:v for n,v in s.items() if n != 'worstArithmeticWitness'} for k,s in result['analysis']['states'].items()},indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs',type=Path,required=True)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();retain(args.runs,args.build,args.out)
