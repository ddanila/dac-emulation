#!/usr/bin/env python3
"""Optional, hash-bound plain-PC1715 startup probe; never claims floppy boot."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = '51cb80639b5667f2611da71ce7305061566cf3474bda7db6fc82709d08e46d01'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('rom', type=Path)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args()
    data = args.rom.read_bytes()
    before = hashlib.sha256(data).hexdigest()
    if len(data) != 2048 or before != EXPECTED:
        p.error('this optional check is qualified only for the documented r1715bt.bin')
    # Reserve the report first so an existing report or input cannot be overwritten.
    with args.report.open('x') as output:
        run = subprocess.run([str(ROOT / 'build/pc1715-probe'), str(args.rom),
                              '10000000'], capture_output=True, text=True,
                             check=True, timeout=30)
        result = json.loads(run.stdout)
        ports = {row['port']: row for row in result['ports']}
        checks = {
            'exact_budget': result['cycles'] == 10000000,
            'overlay_disabled': result['rom_enabled'] == 0,
            'startup_controller_writes': all(ports.get(n, {}).get('writes', 0)
                                             for n in (*range(8), 0x20, 0x28)),
            'in_controller_wait': 0x402 <= result['pc'] <= 0x421,
            'no_disk_boot_claim': result['disk_boot_supported'] is False,
            'input_unchanged': hashlib.sha256(args.rom.read_bytes()).hexdigest() == before,
        }
        report = {'schema': 1, 'rom_sha256': before,
                  'qualification': 'stock ROM startup into missing-controller wait only',
                  'checks': checks, 'passed': all(checks.values()), 'result': result}
        json.dump(report, output, indent=2)
        output.write('\n')
    print('PASS' if report['passed'] else 'FAIL', report['qualification'])
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
