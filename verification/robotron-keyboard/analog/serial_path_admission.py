#!/usr/bin/env python3
"""Keep diagnostic serial-path results separate from physical model admission."""
import argparse
import json
from pathlib import Path

from gate_switching_probe import sha

HERE=Path(__file__).resolve().parent


def assess(root):
    paths={
        'cpu':root/'cpu-drive/report.json',
        'recovery':root/'recovery/report.json',
        'recoveryComparison':root/'recovery/assessment.json',
        'internal':root/'internal/assessment.json',
        'traffic':HERE/'reports/7406-dynamic/traffic/assessment.json',
        'independentDeviceScope':HERE/'reports/7406-dynamic/operating-region-review.json',
        'device':HERE/'reports/7406-dynamic/report.json'}
    data={key:json.loads(path.read_text()) for key,path in paths.items()}
    if not all(data[n]['completed'] for n in ('cpu','recovery','internal','device')):
        raise ValueError('Incomplete investigation')
    if data['recovery']['deviceReportSha256']!=sha(paths['device']) or data['cpu']['deviceReportSha256']!=sha(paths['device']):
        raise ValueError('Mismatched device candidate')
    internal=data['internal'];cpu=data['cpu'];recovery=data['recovery']
    control_preserved=internal['networkByteIdenticalToControl'] and internal['firmwareMatchesControl']
    return dict(completed=True,qualified=False,boardAdmission=False,
        sourceSha256=sha(Path(__file__)),evidence={key:sha(path) for key,path in paths.items()},
        evidenceTiers=dict(
            published=dict(established='Selected datasheet screens and reproducible reference-model behavior.',
                limitation='Fitted junction parameters, filter impedance and CPU I/V remain assumptions, not published device curves.'),
            bench=dict(required=[
                'Measure equivalent driver recovery, reverse current and loaded waveform under the modeled slow-input and filter conditions.',
                'Measure equivalent CPU/bus driver I/V and transitions over the modeled supply and loading range.',
                'Characterize the reference filter, cable and host impedance.'],
                decision='Whether the electrical uncertainty changes host receiver decisions or CPU/bus timing.'),
            specimen=dict(required='Installed identity, actual cable/filter parameters and timing for a specimen claim.',
                blocksFunctionalReference=False)),
        diagnosticScope='Replay initialization failure and internal-current residual are retained research diagnostics; they do not independently block a functional reference release. Their relevance to electrical acceptance depends on terminal and receiver margins.',
        clockGate='Oscillator and CPU clock admission remain separate prerequisites; this investigation does not establish them.',
        unchangedLiveControl=control_preserved,
        internalCurrentBalanceScreen=internal['currentBalanceScreen'],
        inputLevelsPassSampledCpuCases=all(r['levelsPass'] for r in cpu['runs']),
        supplyAnchoredEndpointHypothesisPasses=all(r['passed'] for r in cpu['endpoints']['True']),
        fittedDriverExceedsPublishedSinkTestCurrent=internal['dataCollectorExceedsPublishedSinkTestCurrent'],
        equallyScreenedDeviceSensitivityV=data['recoveryComparison']['sameStepDeviceSensitivity']['maximumDifferenceV'],
        unsuccessfulReplays={name:r['error'] for name,r in recovery['runs'].items() if not r['completed']},
        inputReplayErrorsV={name:r['peakDifferenceFromLiveOutputV'] for name,r in recovery['runs'].items() if r['completed'] and name in ('control','long-prelude','extended-prelude','half-step','quarter-step')},
        precedingReadDriveSample=internal['atMinimum']['lastSampledBusOwnership'],
        observedMechanism='The output transistor enters reverse operation during the loaded filter excursion. Base-collector voltage and stored charge, filter current and cable-ground motion are observed; changing load or filter assumptions changes the result.',
        physicalEvidenceGaps=[
            'Independent L1, cable and host impedance parameters; the load sweep is sensitivity, not a measured range.',
            'SN7406-specific reverse recovery and transient-current behavior; generic fitted transistor charge is not independently validated.',
            'CPU D0/WR and bus-owner I/V, supply dependence and transient behavior; endpoint interpolation does not identify these.'],
        representativeTraffic=dict(preflightPassed=data['traffic']['preflightPassed'],
            electricalExecuted=False,admissionPassed=False,
            reason='Independent physical-model admission remains open. Passing waveform refinement and DC endpoint screens does not authorize qualification traffic.'),
        decision='Retain the original circuit and the diagnostic hypotheses separately. Do not tune a clamp or reduce load solely to remove undershoot. Qualify the loaded driver and CPU boundaries before running representative coupled traffic for acceptance.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
    result=assess(a.root)
    if a.verify:
        if result!=json.loads(a.out.read_text()):raise ValueError('Stale serial-path assessment')
        print('Serial-path assessment verified; physical admission remains open.')
    else:a.out.write_text(json.dumps(result,indent=2)+'\n')
