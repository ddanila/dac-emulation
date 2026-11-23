"""Check page-15 control values against a fresh page-10 assembly and profile."""
import hashlib
import json
from pathlib import Path
import re
import tempfile

import steady_supply

ROOT = Path(__file__).resolve().parent
WORKTREE = ROOT.parent.parent
SOURCE = ROOT / 'reference/k7222-11/page10-control-values-source-read.json'
REPORT = ROOT / 'reference/k7222-11/page10-control-values-comparison.json'
PROFILE = ROOT / 'profiles/k7222-11-vertical-output.json'
MODELS = ROOT / 'circuits/k7222-11-vertical-output-models.cir'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(components):
    source = json.loads(SOURCE.read_text())
    if source['format'] != 'dac-monitor-page10-control-values-source-read-v1':
        raise ValueError('source format changed')
    if (sha(WORKTREE / 'build/monitor/phase-a/sources/older.pdf')
            != source['source']['pdf_sha256']):
        raise ValueError('source PDF changed')
    if (sha(WORKTREE / 'build/monitor/phase-a/page15-600.png')
            != source['source']['view_600dpi_sha256']):
        raise ValueError('parts-list view changed')
    expected = {'R50': (10000, 'fixed_resistor'),
                'R57': (910, 'fixed_resistor'),
                'R58': (470, 'adjustable_resistor'),
                'R59': (47000, 'adjustable_resistor'),
                'R60': (47000, 'adjustable_resistor')}
    if source['board'] != '012-6931' or source['parts'] != {
            name: {'value_ohm': value, 'kind': kind}
            for name, (value, kind) in expected.items()}:
        raise ValueError('parts-list read changed')
    by_id = {part['source_id']: part for part in components}
    actual = {name: by_id['012-6931:' + name]['value'] for name in expected}
    profile = json.loads(PROFILE.read_text())
    params = profile['parameters']
    models = MODELS.read_text()
    checks = {
        'R50_fixed_10k': actual['R50'] == '10k',
        'R57_fixed_910': actual['R57'] == '910',
        'R58_three_terminal_pot': (actual['R58'] == 'VERT_POT'
                                   and len(by_id['012-6931:R58']['nodes']) == 3),
        'R58_total_470': (bool(re.search(r'\{470\*symmetry_fraction\}', models))
                          and bool(re.search(r'\{470\*\(1-symmetry_fraction\)\}', models))),
        'R58_fraction_bounds': (params['symmetry_fraction']['minimum'] > 0
                                and params['symmetry_fraction']['maximum'] < 1),
        'R59_R60_source_maximum': all(
            actual[name] == '{linearity_' + name.lower() + '}'
            and params['linearity_' + name.lower()]['maximum'] == 47000
            and params['linearity_' + name.lower()]['nominal'] == 23500
            and len(by_id['012-6931:' + name]['nodes']) == 2
            for name in ('R59', 'R60')),
    }
    return {'format': 'dac-monitor-page10-control-values-comparison-v1',
            'qualification': 'five parts-list values and model parameterizations; no terminal, wiper, installed-setting or full-page signoff',
            'source_read_sha256': sha(SOURCE), 'profile_sha256': sha(PROFILE),
            'model_sha256': sha(MODELS), 'exported_values': actual,
            'checks': checks, 'passed': all(checks.values()),
            'open': ['R59/R60 are two-terminal rheostat abstractions of 47 kohm listed adjustable parts; physical wiper wiring is unreviewed.',
                     'The controls have no source-terminal read or installed-position evidence.']}


if __name__ == '__main__':
    with tempfile.TemporaryDirectory() as directory:
        components = steady_supply.assemble(Path(directory) / 'assembly')['components']
    result = compare(components)
    REPORT.write_text(json.dumps(result, indent=2) + '\n')
    print(f"page-10 control values: {sum(result['checks'].values())}/{len(result['checks'])} checks")
    raise SystemExit(0 if result['passed'] else 2)
