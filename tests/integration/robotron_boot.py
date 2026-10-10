#!/usr/bin/env python3
"""Optional TOS/M media regression, bounded native runs; no HDL or input writes.

For --file-operations use raw media decoded from the original TeleDisk image,
not the release's damaged tosm10_x/robotron.img. See Robotron README.
"""
import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def files(image):
    """Independent directory reader for the tested SCP3 format (cpmtools 17153).

    4 reserved tracks, 128 entries, 2K blocks, 16-bit allocation IDs, EXM=0.
    Records retain CP/M EOF padding, allowing exact binary comparisons.
    """
    data = image.read_bytes()
    assert len(data) == 819200
    base = 4 * 5 * 1024
    entries = {}
    for pos in range(base, base + 128 * 32, 32):
        e = data[pos:pos + 32]
        if e[0] != 0:  # user zero only; skip labels, timestamps and deleted files
            continue
        name = bytes(x & 127 for x in e[1:9]).decode('ascii').rstrip()
        ext = bytes(x & 127 for x in e[9:12]).decode('ascii').rstrip()
        name = name + ('.' + ext if ext else '')
        blocks = [int.from_bytes(e[i:i+2], 'little') for i in range(16, 32, 2)]
        content = b''.join(data[base + b*2048:base + (b+1)*2048] for b in blocks if b)
        extent = (e[14] & 63) * 32 + (e[12] & 31)
        entries.setdefault(name, []).append((extent, content[:e[15]*128]))
    return {name: b''.join(b for _, b in sorted(parts)) for name, parts in entries.items()}


def main():
    p = argparse.ArgumentParser()
    for name in ('rom', 'prom', 'disk'):
        p.add_argument(name, type=Path)
    p.add_argument('--file-operations', action='store_true')
    p.add_argument('--report', type=Path)
    args = p.parse_args()
    root = Path(__file__).resolve().parents[2]
    inputs = [x.resolve() for x in (args.rom, args.prom, args.disk)]
    identities = {str(x): digest(x) for x in inputs}
    report = {'inputs': identities, 'cases': []}

    def run(name, keys, expected, disk=None, writable=False, export=None):
        cmd = [root/'build/robotron-boot', *inputs[:2], disk or inputs[2], '100000000', keys]
        if writable:
            cmd += ['--writable']
        if export:
            cmd += ['--export', export]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True, timeout=30)
        for text in expected:
            assert text in result.stdout, (name, text, result.stdout, result.stderr)
        assert result.stdout.rstrip().endswith('A>'), (name, result.stdout)
        report['cases'].append({'name': name, 'state': result.stderr.strip(),
                                'screen_sha256': hashlib.sha256(result.stdout.encode()).hexdigest()})
        print('PASS Robotron', name, result.stderr.strip())
        return result

    run('directory', 'DIR\r', ['A>DIR', 'SCP3', 'AUTOEXC'])
    run('type', 'TYPE AUTOEXC.SUB\r', ['MODCS COMMON0', 'FKEY'])
    result = run('delete', 'ERA AUTOEXC.BAK\rDIR AUTOEXC.*\r',
                 ['A>DIR AUTOEXC.*', 'AUTOEXC  SUB'], writable=True)
    assert 'AUTOEXC  BAK' not in result.stdout
    assert re.search(r'writes=[1-9][0-9]*', result.stderr)

    if args.file_operations:
        original = files(inputs[2])
        assert original['PIP.COM'][0] == 0xc9, 'Expected original TOS/M PIP header; decode the TD0 image'
        with tempfile.TemporaryDirectory(prefix='dac-files-') as tmp:
            created, deleted, readonly = [Path(tmp)/s for s in ('created.img', 'deleted.img', 'readonly.img')]
            run('create-read-copy', 'PIP DAC.TXT=CON:\rDAC REGRESSION\r\x1aTYPE DAC.TXT\r'
                'PIP DAC2.TXT=DAC.TXT\rPIP DAC.COM=PIP.COM\r',
                ['A>TYPE DAC.TXT', 'DAC REGRESSION', 'A>PIP DAC.COM=PIP.COM'],
                writable=True, export=created)
            content = files(created)
            assert content['DAC.TXT'].split(b'\x1a')[0] == b'DAC REGRESSION\r'
            assert content['DAC2.TXT'] == content['DAC.TXT']
            assert content['DAC.COM'] == original['PIP.COM']
            for name, data in original.items():
                assert content[name] == data, ('unrelated file modified', name)
            # A fresh boot reads the exported disk before deleting all new files.
            run('reboot-read-delete', 'TYPE DAC2.TXT\rERA DAC.TXT\rERA DAC.COM\rERA DAC2.TXT\rDIR DAC*.*\r',
                ['DAC REGRESSION', 'A>DIR DAC*.*'], disk=created, writable=True, export=deleted)
            assert files(deleted) == original
            run('read-only', 'ERA AUTOEXC.BAK\r', [], export=readonly)
            assert readonly.read_bytes() == inputs[2].read_bytes()
            report['copied_binary_sha256'] = hashlib.sha256(content['DAC.COM']).hexdigest()
    assert identities == {str(x): digest(x) for x in inputs}, 'input media modified'
    if args.report:
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
