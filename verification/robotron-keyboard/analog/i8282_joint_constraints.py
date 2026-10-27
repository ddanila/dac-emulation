#!/usr/bin/env python3
"""Intersect retained I8282 electrical constraints without admitting a device."""
import argparse
import json
import math
from pathlib import Path

import i8282_enabled_candidates as enabled
import i8282_capacitance_probe as capacitance
import i8282_propagation_probe as propagation
import i8282_release_probe as release
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent
REPORTS = {
    'enabled': ('i8282-enabled-candidates', enabled),
    'capacitance': ('i8282-capacitance-candidates', capacitance),
    'propagation': ('i8282-propagation-candidates', propagation),
    'release': ('i8282-release-candidates', release),
}
FIELDS = {
    'data': 'maximumInternalDataDelaySeconds',
    'strobe': 'maximumInternalStrobeDelaySeconds',
    'disconnect': 'maximumInternalDisconnectSeconds',
}


def assess(root):
    reports = {}
    receipts = {}
    for key, (name, module) in REPORTS.items():
        folder = root / name
        module.verify(folder)  # Replay measurements, decks, conditions and hashes.
        reports[key] = json.loads((folder / 'assessment.json').read_text())
        receipts[name] = sha(folder / 'assessment.json')
    groups = []
    for resistance in enabled.HIGH_OHMS:
        for cap in capacitance.EXTRA_PF:
            def selected(kind):
                return [(i, row['case']) for i, row in enumerate(reports[kind]['cases'])
                        if row['case']['highOhms'] == resistance
                        and row['case']['extraCapacitancePf'] == cap]
            edge = selected('capacitance')
            failures = [i for i, c in edge if not c['withinPublishedLimit']]
            bounds = {}
            for kind, field in FIELDS.items():
                source = 'release' if kind == 'disconnect' else 'propagation'
                i, c = min(selected(source), key=lambda item: item[1][field])
                bounds[kind] = {'minimumSeconds': 0.0, 'maximumSeconds': c[field],
                               'report': REPORTS[source][0], 'caseIndex': i}
            groups.append({
                'highOhms': resistance, 'extraCapacitancePf': cap,
                'edgeConstraintsPassed': not failures,
                'failedCapacitanceCaseIndices': failures,
                'internalDelayIntervals': bounds if not failures else None,
                'delayBudgetsBeforeEdgeRejection': bounds,
                'caseCounts': {key: len(selected(key)) for key in ('capacitance', 'propagation', 'release')},
            })
    sources = {'i8282_joint_constraints.py', 'i8282_enable_comparison.json'}
    for _, module in REPORTS.values():
        sources.update(module.SOURCES)
    return {
        'completed': True, 'qualified': False, 'deviceAdmitted': False,
        'scope': 'Intersection for the retained constant-resistance hypotheses at the three tested supplies, both edge polarities and all retained release leakage cases. No interpolation to untested capacitances or temperatures.',
        'delayConvention': 'Nonnegative constant pure transport delay before an instantaneous drive transition or disconnect. Upper endpoints are analytic pin-limit remainders, not measured internal delays. Finite internal slew requires a new joint test.',
        'notEstablished': ['Intel enable measurement convention and enable dynamics',
                           'Nonlinear I/V, temperature behavior and internal slew',
                           'CPU/ROM alternatives, operational bus integration and specimen applicability'],
        'sourceReports': receipts,
        'sources': {name: sha(HERE / name) for name in sorted(sources)},
        'alternatives': groups,
    }


def check_delays(report, resistance, capacitance_pf, **delays):
    """Validate a proposed adapter's partial parameter set, never device admission."""
    if set(delays) != set(FIELDS):
        raise ValueError('Require data, strobe and disconnect delays; enable is unresolved')
    matches = [row for row in report['alternatives']
               if row['highOhms'] == resistance and row['extraCapacitancePf'] == capacitance_pf]
    if len(matches) != 1 or matches[0]['internalDelayIntervals'] is None:
        raise ValueError('Untested or rejected resistance/capacitance combination')
    for name, value in delays.items():
        bound = matches[0]['internalDelayIntervals'][name]
        if not math.isfinite(value) or not bound['minimumSeconds'] <= value <= bound['maximumSeconds']:
            raise ValueError('Internal ' + name + ' delay exceeds joint budget')
    return {'partialConstraintsPassed': True, 'deviceAdmitted': False, 'enableQualified': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reports', type=Path, default=HERE / 'reports')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    result = assess(args.reports)
    if args.check:
        if json.loads(args.out.read_text()) != result:
            raise ValueError('Changed joint constraint evidence')
    else:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        with args.out.open('x') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
    print('Joint constraints verified; enable and complete device admission remain open.')
