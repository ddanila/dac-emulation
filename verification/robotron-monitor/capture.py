#!/usr/bin/env python3
"""Capture functional emulator video with immutable input and executable hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from lab import parse_capture

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('rom','prom','disk','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--chargen',type=Path)
    parser.add_argument('--boot-ticks',type=int,default=32_000_000)
    parser.add_argument('--dot-ticks',type=int,default=13_824_000,
                        help='capture length in 13.824 MHz dot ticks (default one second, for settled 16-field rendering)')
    args=parser.parse_args()
    executable=ROOT/'build/robotron-monitor-capture'
    files={'rom':args.rom,'prom':args.prom,'disk':args.disk,'executable':executable}
    if args.chargen:files['chargen']=args.chargen
    hashes={name:hashlib.sha256(path.read_bytes()).hexdigest() for name,path in files.items()}
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'capture.json'
        subprocess.run([str(executable),str(args.rom),str(args.prom),str(args.chargen) if args.chargen else '-',str(args.disk),str(args.boot_ticks),str(args.dot_ticks),str(path)],check=True,timeout=120)
        data=parse_capture(path)
        data['input_sha256']=hashes
        # Refuse races and accidental replacement of a recorded experiment.
        with args.output.open('x') as stream:json.dump(data,stream,separators=(',',':'));stream.write('\n')


if __name__=='__main__':main()
