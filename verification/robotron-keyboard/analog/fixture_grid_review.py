#!/usr/bin/env python3
"""Retain matched fixture-scheduling controls and absolute-time refinement."""
import argparse
import json
import lzma
import re
import shutil
from pathlib import Path
from reset_release_driver_review import trace_summary, completed, TRACES
from live_transition_review import diagnostic
from host_waveform_comparison import rows, compare_samples
from numerical_voltage_budget import voltage_gate
from network_refinement_review import events
from ttl7406_probe import sha
from common_samples import samples_at, compare_native
from local_refinement_grid import grids

HERE = Path(__file__).resolve().parent
CASES = ('control', '25', '12.5', '6.25')


def validate_receipts(receipts, experiment):
    # Only the declared experimental variable and maximum timestep may differ.
    ignored = {'elapsedSeconds', 'exitCode', 'timedOut', 'solverDiagnostic', 'deckSha256',
               'stepNs', 'fixtureCrossingGuardPs', 'method', 'samplingGridSha256'}
    if experiment in ('dac-anchored','dense-anchored'):ignored.add('dacAnchored')
    if experiment == 'transient-error': ignored.add('truncationTolerance')
    identity = lambda run: {k: v for k, v in run.items() if k not in ignored}
    if experiment not in ('crossings','integration','sampling','tight-passive','nested-local','dac-anchored','dense-anchored','transient-error'):raise ValueError('Unknown experiment')
    base=receipts['25'] if experiment=='tight-passive' else receipts['control']
    expected_grid=receipts['25'].get('samplingGridSha256') if experiment in ('sampling','tight-passive') else None
    if experiment in ('sampling','tight-passive') and not expected_grid:raise ValueError('Missing sampling grid')
    for name, run in receipts.items():
        if experiment == 'transient-error':
            if not run.get('dacAnchored') or run.get('haltNs') is not None or any(run.get(k, False) for k in ('dacStateAudit','startupTruncAudit','filterTruncAudit')):
                raise ValueError('Unexpected transient-error controls')
            if run.get('truncationTolerance') != (1 if name == 'control' else .25):
                raise ValueError('Unexpected transient-error tolerance')
        elif experiment in ('dac-anchored','dense-anchored'):
            if run.get('dacAnchored')!=(name!='control') or run.get('haltNs') is not None or run.get('dacStateAudit',False) or run.get('startupTruncAudit',False):
                raise ValueError('Unexpected anchored DAC controls')
        elif run.get('dacAnchored',False):raise ValueError('Undeclared anchored DAC')
        if experiment in ('dense-anchored','transient-error') and run.get('stopNs')!=1006000:
            raise ValueError('Dense candidate requires the complete reset-release window')
        if experiment in ('nested-local','dac-anchored','dense-anchored','transient-error'):
            if not run.get('samplingGridSha256'):raise ValueError('Missing nested grid')
        elif run.get('samplingGridSha256') != (None if name=='control' else expected_grid):
            raise ValueError('Unmatched sampling grid')
        if identity(run) != identity(base):
            raise ValueError('Unmatched runtime, circuit or experimental controls')
        expected_method = 'gear' if experiment == 'integration' and name != 'control' else 'trap'
        if run['method'] != expected_method:
            raise ValueError('Unexpected integration method')
        if run['fixtureCrossingGuardPs'] != (None if name == 'control' and experiment == 'crossings' else .25):
            raise ValueError('Unexpected scheduling guard')
        if run['stepNs'] != (25 if name == 'control' else float(name)):
            raise ValueError('Unexpected refinement step')
        if experiment in ('tight-passive','nested-local','dac-anchored','dense-anchored','transient-error') and (run['toleranceScale']!=(.01 if experiment in ('dense-anchored','transient-error') else .1) or run['toleranceComponents']!=['reltol'] or run['mpfrStartNs']!=0 or run['mpfrTransitionBits']!='256' or not run['conservativeCap'] or not run['passiveAssembly']):
            raise ValueError('Unexpected tight passive candidate')


def validate_anchor_grids(receipts, experiment):
    if experiment not in ('dac-anchored','dense-anchored','transient-error'):
        raise ValueError('Expected anchored experiment')
    original=HERE/('reports/startup-tight-tolerance' if experiment in ('dense-anchored','transient-error') else 'reports/nested-local-refinement')
    for name,run in receipts.items():
        prior='25' if name=='control' else name
        if run['samplingGridSha256']!=sha(original/prior/'sampling-grid.json'):
            raise ValueError('Anchored candidate changed the retained grid')


def retain_generator(candidates, out, expected_digest):
    """Preserve the source that actually produced the capture, not a newer runner."""
    for candidate in candidates:
        if candidate.is_file() and sha(candidate) == expected_digest:
            target = out / 'capture-generator.py'
            shutil.copyfile(candidate, target)
            if sha(target) != expected_digest:
                raise ValueError('Changed capture generator during retention')
            return {'path': target.name, 'sha256': expected_digest}
    raise ValueError('Missing hash-matched capture generator')


def validate_anchor_build(run, build):
    models=[m for m in run['runtime']['codeModels'] if Path(m['path']).name=='digital.cm']
    if len(models)!=1 or models[0]['sha256']!=build['outputs']['digital.cm'] or run['runtime']['spinit']['sha256']!=build['outputs']['spinit']:
        raise ValueError('Anchored build does not match runtime')
    if build.get('dacAnchorHeaderSha256')!=sha(HERE/'engine-patches/dac_anchor.h') or build['patches'].get('dac-anchored-ramp.patch')!=sha(HERE/'engine-patches/dac-anchored-ramp.patch'):
        raise ValueError('Unexpected anchored arithmetic source')


def validate_nested_inputs(decks, sampling, assessment, stop_ns):
    expected=grids(assessment,sampling['control'],stop_ns)
    for name,grid in zip(('25','12.5','6.25'),expected):
        for key,value in grid.items():
            if sampling[name].get(key)!=value:
                raise ValueError('Unexpected local grid: '+name+' '+key)
    validate_grid_decks(decks)


def validate_grid_decks(decks):
    normalized=set()
    for deck in decks.values():
        # Only the isolated breakpoint source and maximum timestep may vary.
        stripped,count=re.subn(r'^Vsampling_grid sampling_grid 0 PWL\(0 0\n(?:\+ [^\n]*\n)*?\+ \)\n',
                               '<sampling-grid>\n',deck,flags=re.M)
        if count!=1:raise ValueError('Missing or ambiguous isolated grid source')
        normalized.add(re.sub(r'^\.tran\s+\S+', '.tran <step>',stripped,flags=re.M))
    if len(normalized)!=1:raise ValueError('Nested decks differ beyond timestep and grid')


def strip_truncation_option(deck, expected):
    line = f'.options trtol={expected:.17g}\n'
    if deck.count(line) != 1:
        raise ValueError('Missing or ambiguous transient-error option')
    stripped = deck.replace(line, '', 1)
    if re.search(r'\b(?:xtrtol|trtol)\b', stripped, re.I):
        raise ValueError('Additional transient-error option')
    return stripped


def validate_truncation_decks(decks):
    validate_grid_decks({name:strip_truncation_option(deck, 1 if name=='control' else .25)
                         for name,deck in decks.items()})


def validate_truncation_baseline(run, deck):
    root = HERE/'reports/dense-anchored-refinement/25'
    base = json.loads((root/'run.json').read_text())
    ignored = {'elapsedSeconds','generatorSha256','deckSha256','truncationTolerance','filterTruncAudit'}
    if run.get('truncationTolerance') != 1 or run.get('filterTruncAudit', False):
        raise ValueError('Unexpected explicit baseline')
    if {k:v for k,v in run.items() if k not in ignored} != {k:v for k,v in base.items() if k not in ignored}:
        raise ValueError('Explicit baseline changed inputs or runtime')
    if strip_truncation_option(deck,1) != (root/'io.cir').read_text():
        raise ValueError('Explicit baseline changed the circuit')


def bus_if_complete(log, complete):
    return events(log) if complete else None


def retain(root, out, experiment="crossings"):
    case_names=('25','12.5','6.25') if experiment=='tight-passive' else CASES
    def source(name):
        if experiment == 'transient-error':
            return root / ('trtol-tight-full-' + name)
        if experiment == "dense-anchored":
            return root / ("dense-tight-full-"+("disabled" if name=="control" else name))
        if experiment == "dac-anchored":
            return root / ("dac-anchored-full-"+("disabled" if name=="control" else name))
        if experiment == "nested-local":
            return root / ("tight-passive-full-25" if name == "control" else "nested-local-full-"+name)
        if experiment == "tight-passive":
            return root / ("tight-passive-full-"+name)
        if experiment == "sampling":
            return root / ("fixture-grid-sampling-"+name)
        if experiment == "integration":
            return root / ("fixture-grid-reset-25" if name == "control" else "fixture-grid-gear-"+name)
        return root / ("fixture-grid-reset-"+name)
    out.mkdir(parents=True, exist_ok=False)
    receipts, cases = {}, {}
    for name in case_names:
        src = source(name)
        dst = out / name
        dst.mkdir()
        run = json.loads((src / 'run.json').read_text())
        receipts[name] = run
        if not run.get('externalDependencies') or sha(src / 'io.cir') != run['deckSha256']:
            raise ValueError('Missing dependencies or changed deck')
        for file, digest in run['inputs'].items():
            if sha(src / file) != digest:
                raise ValueError('Changed input')
        if run.get('samplingGridSha256'):
            if sha(src/'sampling-grid.json')!=run['samplingGridSha256']:raise ValueError('Changed sampling grid')
            shutil.copyfile(src/'sampling-grid.json',dst/'sampling-grid.json')
        for file in ('io.cir', 'run.json'):
            shutil.copyfile(src / file, dst / file)
        log = (src / 'ngspice.log').read_text()
        with lzma.open(dst / 'ngspice.log.xz', 'wt') as stream:
            stream.write(log)
        traces = {file: trace_summary(src / file) for file in TRACES if any(Path(str(src/file)+suffix).exists() for suffix in ('','.gz','.xz'))}
        (dst / 'trace-endpoints.json').write_text(json.dumps(traces, indent=2) + '\n')
        complete=completed(run, traces, diagnostic(log))
        cases[name] = {'completed': complete,
                       'diagnostic': diagnostic(log), 'timedOut': run['timedOut'],
                       'bus': bus_if_complete(log,complete)}
    validate_receipts(receipts, experiment)
    if experiment=='tight-passive':
        decks={re.sub(r'^\.tran\s+\S+', '.tran <step>',(source(name)/'io.cir').read_text(),flags=re.M) for name in case_names}
        if len(decks)!=1:raise ValueError('Refinement decks differ beyond timestep')
    if experiment in ('nested-local','dac-anchored'):
        validate_nested_inputs({name:(source(name)/'io.cir').read_text() for name in case_names},
            {name:json.loads((source(name)/'sampling-grid.json').read_text()) for name in case_names},
            json.loads((HERE/'reports/tight-passive-refinement/assessment.json').read_text()), receipts['25']['stopNs'])
    if experiment in ('dac-anchored','dense-anchored','transient-error'):
        if experiment == 'transient-error':
            validate_truncation_decks({name:(source(name)/'io.cir').read_text() for name in case_names})
            validate_truncation_baseline(receipts['control'], (source('control')/'io.cir').read_text())
        if experiment=='dense-anchored':
            validate_grid_decks({name:(source(name)/'io.cir').read_text() for name in case_names})
        validate_anchor_grids(receipts, experiment)
        build_path=Path(receipts['25']['runtime']['spinit']['path']).parent/'build.json'
        validate_anchor_build(receipts['25'],json.loads(build_path.read_text()))
        shutil.copyfile(build_path,out/'build.json')
    pairs = []
    for a, b in (('control', '25'), ('25', '12.5'), ('12.5', '6.25')):
        if a not in cases or b not in cases or not (cases[a]['completed'] and cases[b]['completed']):
            continue
        signals = receipts[a]['observationSignals']
        result = compare_samples(*(rows(source(name) / 'network_witness.txt',
                                       signals, receipts[name]['stepNs']) for name in (a, b)))
        ea, eb = cases[a]['bus'], cases[b]['bus']
        pairs.append({'coarse': a, 'fine': b, 'endSeconds': result['endSeconds'],
            'signals': {signal: {'unit': 'V' if signal.lower().startswith('v(') else 'A',
                'maximumAbsoluteDifference': value['maximumDifferenceV'], 'timeSeconds': value['timeSeconds']}
                for signal, value in zip(signals, result['signals'])},
            'busEventsIdentical': ea == eb, 'busSamplesIdentical': ea['samples'] == eb['samples'],
            'busEdgeTimingDifferencePs': [y-x for x,y in zip(ea['edgeTimesPs'],eb['edgeTimesPs'])]
                if len(ea['edgeTimesPs']) == len(eb['edgeTimesPs']) else None,
            'latchesMatch': ea['latchesMatch'] and eb['latchesMatch']})
    common=None
    if experiment in ('sampling','tight-passive','nested-local','dac-anchored','dense-anchored','transient-error'):
        times=json.loads((source('25')/'sampling-grid.json').read_text())['timesSeconds']
        signals=receipts['25']['observationSignals']
        common={'signals':signals,'samples':{name:samples_at(rows(source(name)/'network_witness.txt',signals,receipts[name]['stepNs']),times) for name in case_names if cases[name]['completed']},
            'scope':'Actual nearest saved samples with explicit time offsets; no interpolation. Added breakpoints can change solver trajectory. These selected times do not substitute for the full-window gate.'}
        common['comparisons']=[{'coarse':a,'fine':b,**compare_native(common['samples'][a],common['samples'][b],signals)}
            for a,b in (('25','12.5'),('12.5','6.25')) if a in common['samples'] and b in common['samples']]
    control = next((pair for pair in pairs if pair['coarse'] == 'control'), None)
    pairs = [pair for pair in pairs if pair['coarse'] != 'control']
    result = {'schema': 1, 'experiment': experiment, 'commonSamples': common, 'cases': cases, 'controlComparison': control, 'refinementPairs': pairs,
        'voltageGate': voltage_gate(pairs) if len(pairs) == 2 else None,
        'numericallyQualified': False, 'electricallyQualified': False,
        'productionDefaultChangeAuthorized': False,
        'scope': 'Bounded live prefix with ideal external clock/reset. Matched precision window and fixed crossing guard; no physical board-model or tolerance changes. Isolated grid sources change scheduling and solver matrix structure, so their control comparison does not isolate scheduling alone. Trace tails and hashes retain provenance; full raw waveforms remain in local run directories. This cannot qualify full-repeat traffic or physical device models.',
        'sources': {name: sha(HERE / name) for name in ('fixture_grid_review.py', 'fixture_crossing_grid.py',
            'live_transition_probe.py', 'reset_release_driver_review.py', 'live_transition_review.py',
            'host_waveform_comparison.py', 'network_refinement_review.py', 'numerical_voltage_budget.py', 'trace_io.py', 'sampling_grid.py', 'common_samples.py')}}
    if experiment in ('nested-local','dac-anchored','dense-anchored','transient-error'):
        result['sources']['local_refinement_grid.py']=sha(HERE/'local_refinement_grid.py')
        result['scope']='Matched tight passive candidate with nested requested local breakpoints and maximum-step refinement. Actual adaptive meshes need not be nested. The control retains the original common grid. All comparisons cover the full observation window; this prefix cannot qualify full-repeat traffic or physical device models.'
    if experiment=='dac-anchored':
        result['sources'].update({n:sha(HERE/n) for n in ('engine-patches/dac_anchor.h','engine-patches/dac-anchored-ramp.patch')})
        original=json.loads((HERE/'reports/nested-local-refinement/25/trace-endpoints.json').read_text())
        current=json.loads((out/'control/trace-endpoints.json').read_text())
        result['disabledTracesMatchOriginal']={n:current[n]['sha256']==v['sha256'] for n,v in original.items() if n in current}
        result['scope']='Full reset-release prefix with the opt-in anchored DAC; all captures use the same instrumentable library and the control disables only anchored arithmetic. Original nested grids, physical circuit, firmware and numerical settings are preserved. Full-repeat traffic, complete coupled rollback and physical admission remain separate. No peak omission, phase alignment or gate relaxation.'
    if experiment=='dense-anchored':
        result['captureGenerator']=retain_generator(
            (HERE/'live_transition_probe.py', root/'dense-tight-runner.py'),
            out, receipts['25']['generatorSha256'])
        result['sources'].update({n:sha(HERE/n) for n in ('engine-patches/dac_anchor.h','engine-patches/dac-anchored-ramp.patch')})
        result['scope']='Full reset-release window with anchored DAC, retained dense-startup grids and fixed tighter relative tolerance. The control disables only anchored arithmetic. All levels require identical physical inputs and runtime dependencies; no alignment, omitted spans or relaxed voltage gate. Full-repeat, coupled rollback and physical admission remain separate.'
    if experiment == 'transient-error':
        result['captureGenerator'] = retain_generator((root/'trtol-runner.py',), out, receipts['25']['generatorSha256'])
        result['sources'].update({n:sha(HERE/n) for n in ('transient_error_control.py','engine-patches/dac_anchor.h','engine-patches/dac-anchored-ramp.patch')})
        original = json.loads((HERE/'reports/dense-anchored-refinement/25/trace-endpoints.json').read_text())
        current = json.loads((out/'control/trace-endpoints.json').read_text())
        result['explicitDefaultMatchesImplicit'] = {n:n in current and current[n]['sha256']==original[n]['sha256'] for n in TRACES}
        if not cases['control']['completed'] or not all(result['explicitDefaultMatchesImplicit'].values()):
            raise ValueError('Explicit default does not reproduce the complete implicit baseline')
        result['baselineAssessmentSha256'] = sha(HERE/'reports/dense-anchored-refinement/assessment.json')
        result['scope'] = 'Full reset-release window with fixed circuit, Newton tolerances, runtime and retained sampling grids. Explicit trtol=1 must reproduce the implicit XSPICE baseline; the candidate changes only trtol to 0.25. Compare both successive timestep refinements over the full window without alignment or omitted peaks. Full-repeat, coupled rollback and physical admission remain separate.'
    if experiment=='tight-passive':
        result['startupControls']={'path':'reports/startup-passive/assessment.json','sha256':sha(HERE/'reports/startup-passive/assessment.json')}
        result['scope']='Tighter-relative-tolerance live prefix with precision from zero and exact capacitor/later passive additions. Only maximum timestep varies across these captures. Preserved startup controls remain separate; completing this prefix does not qualify full-repeat traffic, production defaults or physical device models.'
    (out / 'assessment.json').write_text(json.dumps(result, indent=2) + '\n')
    if experiment in ('dense-anchored','transient-error') and len(pairs) == 2:
        from sampling_error_review import build as sampling_review
        sampling = sampling_review(root, out, 'trtol-tight-full-' if experiment == 'transient-error' else 'dense-tight-full-')
        (out / 'sampling-error.json').write_text(json.dumps(sampling, indent=2) + '\n')
    manifest = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--experiment', choices=('crossings','integration','sampling','tight-passive','nested-local','dac-anchored','dense-anchored','transient-error'), default='crossings')
    args = parser.parse_args()
    if args.check:
        for name, digest in json.loads((args.out / 'manifest.json').read_text()).items():
            if sha(args.out / name) != digest:
                raise ValueError('Changed retained evidence: ' + name)
        print('Fixture-grid evidence hashes verified')
    else:
        if args.runs is None:
            parser.error('--runs is required')
        result = retain(args.runs, args.out, args.experiment)
        print(json.dumps(result['cases'], indent=2))
