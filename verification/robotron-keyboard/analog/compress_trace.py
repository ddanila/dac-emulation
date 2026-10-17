#!/usr/bin/env python3
"""Losslessly compact completed, hash-pinned waveforms; never touch active runs."""
import argparse
import gzip
import hashlib
import json
import lzma
import shutil
from pathlib import Path

from compare_firmware_io import sha
from trace_io import open_binary


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directories', nargs='+', type=Path)
    p.add_argument('--format', choices=('gzip', 'xz'), default='xz')
    args = p.parse_args()
    for directory in args.directories:
        report = json.loads((directory / 'report.json').read_text())
        if report.get('passed') is not True or report.get('preparedOnly'):
            raise ValueError('Only completed successful runs may be compressed')
        for name, key in [('trace.txt', 'traceSha256'), ('led-trace.txt', 'ledTraceSha256')]:
            source = directory / name
            if key not in report:
                continue
            original = source
            if not original.exists() and args.format == 'xz':
                original = Path(str(source) + '.gz')
            if not original.exists():
                continue
            if sha(source) != report[key]:
                raise ValueError('Original waveform hash differs: ' + str(source))
            suffix = '.xz' if args.format == 'xz' else '.gz'
            target = source.with_name(name + suffix)
            if target.exists():
                raise ValueError('Compressed waveform already exists: ' + str(target))
            temporary = source.with_name(name + suffix + '.tmp')
            compressor = (lambda p: lzma.open(p, 'wb', preset=1)) if args.format == 'xz' else (lambda p: gzip.open(p, 'wb', compresslevel=1))
            decompressor = lzma.open if args.format == 'xz' else gzip.open
            try:
                with open_binary(source) as reader, compressor(temporary) as writer:
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
                digest = hashlib.sha256()
                with decompressor(temporary, 'rb') as reader:
                    for chunk in iter(lambda: reader.read(1024 * 1024), b''):
                        digest.update(chunk)
                if digest.hexdigest() != report[key] or sha(source) != report[key]:
                    raise ValueError('Waveform changed or compression verification failed')
                temporary.replace(target)
                original.unlink()
                print(target, flush=True)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
