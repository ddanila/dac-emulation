#!/usr/bin/env python3
"""Screen a locally supplied TI SDLM056 archive; vendor contents are not retained."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ANALOG = HERE.parents[1]
sys.path.insert(0, str(ANALOG))
from failure_evidence import solver_diagnostic

ARCHIVE_SHA = 'aae641a551b174c2bb5eb84d6ca5e1ac42155a863b9de377e7ca9d8d5f7b8708'
MODEL_SHA = '1e00d760f03681f72627bae69a9f2e7ceac12c8649d3e8a4d55e9b7b687ae532'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--codemodel-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if sha(args.archive) != ARCHIVE_SHA:
        parser.error('Archive differs from the reviewed TI download')
    with zipfile.ZipFile(args.archive) as archive:
        model = archive.read('SN74LS06.cir')
    if hashlib.sha256(model).hexdigest() != MODEL_SHA:
        parser.error('Vendor model hash mismatch')
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    executable = args.ngspice.resolve()
    libraries = sorted(args.codemodel_dir.resolve().glob('*.cm'))
    if not libraries:
        parser.error('No XSPICE code models found')
    (out / 'SN74LS06.cir').write_bytes(model)
    (out / 'spinit').write_text('set ngbehavior=ps\n' + ''.join(
        f'codemodel {path}\n' for path in libraries))
    limits = json.loads((ANALOG / 'ttl7406_limits.json').read_text())
    case = next(c for c in limits['cases'] if c['name'] == 'sink-16ma')
    report = {
        'completed': False, 'qualified': False,
        'sourceUrl': 'https://www.ti.com/lit/zip/SDLM056',
        'archiveSha256': ARCHIVE_SHA, 'modelSha256': MODEL_SHA,
        'runnerSha256': sha(Path(__file__)),
        'limitsSha256': sha(ANALOG / 'ttl7406_limits.json'),
        'diagnosticScannerSha256': sha(ANALOG / 'failure_evidence.py'),
        'runtime': {'executableSha256': sha(executable),
                    'version': subprocess.check_output([str(executable), '--version'], text=True),
                    'codemodels': {str(p): sha(p) for p in libraries}},
        'cases': {}, 'artifacts': {'spinit': sha(out / 'spinit')},
    }
    try:
        for vin in (case['inputVolts'], 3):
            name = f'input-{vin:g}'
            directory = out / name
            directory.mkdir()
            deck = '\n'.join([
                'TI behavioral model DC admission screen', '.include ../SN74LS06.cir',
                '.temp 25', '.options reltol=1e-8 vntol=1e-10 abstol=1e-15',
                f"VCC vp 0 {case['supplyVolts']}", f'VIN a 0 {vin}',
                f"ILOAD 0 y {case['injectedOutputAmps']}",
                f"RLOAD vp y {case['pullupOhms']}", 'Xdut y a vp 0 SN74LS06',
                '.control', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=17',
                'op', 'wrdata trace.txt v(a) v(y) i(VCC) i(VIN)', 'quit', '.endc', '.end', ''])
            (directory / 'probe.cir').write_text(deck)
            result = subprocess.run([str(executable), '-n', '-b', 'probe.cir'],
                cwd=directory, env=dict(os.environ, SPICE_SCRIPTS=str(out)),
                capture_output=True, text=True, timeout=60)
            log = result.stdout + result.stderr
            (directory / 'ngspice.log').write_text(log)
            result.check_returncode()
            if solver_diagnostic(log):
                raise ValueError(solver_diagnostic(log))
            rows = (directory / 'trace.txt').read_text().splitlines()
            if len(rows) != 2:
                raise ValueError('Expected one operating point')
            values = list(map(float, rows[1].split()))
            if len(values) != 5 or not all(map(math.isfinite, values)):
                raise ValueError('Invalid operating point')
            report['cases'][name] = {
                'inputVolts': vin, 'outputVolts': values[2],
                'publishedCondition': vin == case['inputVolts'],
                'maximumOutputVolts': case['maximum'],
                'withinLowOutputLimit': case['minimum'] <= values[2] <= case['maximum'],
            }
            for filename in ('probe.cir', 'trace.txt', 'ngspice.log'):
                report['artifacts'][f'{name}/{filename}'] = sha(directory / filename)
        report['completed'] = True
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n')
        (out / 'SN74LS06.cir').unlink()
    print(json.dumps(report['cases'], indent=2))


if __name__ == '__main__':
    main()
