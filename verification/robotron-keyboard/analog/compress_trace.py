#!/usr/bin/env python3
"""Losslessly compact completed, hash-pinned waveforms; never touch active runs."""
import argparse
import gzip
import hashlib
import json
import shutil
from pathlib import Path

from compare_firmware_io import sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directories', nargs='+', type=Path)
    args = p.parse_args()
    for directory in args.directories:
        report = json.loads((directory / 'report.json').read_text())
        if report.get('passed') is not True or report.get('preparedOnly'):
            raise ValueError('Only completed successful runs may be compressed')
        for name, key in [('trace.txt', 'traceSha256'), ('led-trace.txt', 'ledTraceSha256')]:
            source = directory / name
            if key not in report or not source.exists():
                continue
            if sha(source) != report[key]:
                raise ValueError('Original waveform hash differs: ' + str(source))
            target = source.with_name(name + '.gz')
            if target.exists():
                raise ValueError('Compressed waveform already exists: ' + str(target))
            temporary = source.with_name(name + '.gz.tmp')
            try:
                with source.open('rb') as reader, gzip.open(temporary, 'wb', compresslevel=1) as writer:
                    shutil.copyfileobj(reader, writer, 1024 * 1024)
                digest = hashlib.sha256()
                with gzip.open(temporary, 'rb') as reader:
                    for chunk in iter(lambda: reader.read(1024 * 1024), b''):
                        digest.update(chunk)
                if digest.hexdigest() != report[key] or sha(source) != report[key]:
                    raise ValueError('Waveform changed or compression verification failed')
                temporary.replace(target)
                source.unlink()
                print(target, flush=True)
            finally:
                temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
