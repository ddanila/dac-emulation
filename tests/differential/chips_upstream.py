#!/usr/bin/env python3
"""Run pinned upstream instruction/interrupt suites against our vendored Z80."""
import argparse,os,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args();source=a.source.resolve()
expected='3785836e76c43922f78a50e1f8adfed259ab9672'
assert subprocess.check_output(['git','-C',source,'rev-parse','HEAD'],text=True).strip()==expected,'Use the documented chips-test revision'
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory() as tmp:
 for name in ('z80-test','z80-int'):
  binary=Path(tmp)/name
  subprocess.run([os.environ.get('CC','cc'),'-O2','-I'+str(root/'third_party/cpu'),'-I'+str(source/'tests'),source/'tests'/f'{name}.c','-o',binary],check=True,timeout=30)
  subprocess.run([binary],check=True,timeout=10)
