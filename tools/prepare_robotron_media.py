#!/usr/bin/env python3
"""Convert an externally supplied 256-byte CAS-PROM hex dump to raw bytes."""
import argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('hex',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
data=bytes(int(x,16) for x in a.hex.read_text().split())
if len(data)!=256:raise SystemExit('Expected exactly 256 hexadecimal bytes')
with a.output.open('xb') as f:f.write(data)
print(a.output)
