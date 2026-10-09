#!/usr/bin/env python3
"""Fast compatible-subset boot comparison; no HDL simulation."""
import argparse, subprocess, tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);args=p.parse_args()
root=Path(__file__).resolve().parents[2]
rom=args.source.resolve()/'spinoffs/minimal-vga/roms/ekta37_z80.bin'
with tempfile.TemporaryDirectory() as d:
 work=Path(d)
 subprocess.run([root/'build/juku-trace',rom,'50000000','6000'],cwd=work,check=True,timeout=10,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for mode in (0,1):
  subprocess.run([root/'build/vjuga-boot',rom,work/'z80.bin',str(mode)],check=True,timeout=10)
  assert (work/'z80.bin').read_bytes()==(work/'vram.bin').read_bytes(),mode
print('PASS: VJUGA native Z80 framebuffer matches bounded Juku oracle in both modes')
