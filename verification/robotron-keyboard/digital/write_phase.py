#!/usr/bin/env python3
"""Test the existing TV80 T2Write parameter without changing production or vendored RTL."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,BOARD,sha,parse,assess
p=argparse.ArgumentParser();p.add_argument('capture',type=Path);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.mkdir(parents=True,exist_ok=False)
parent=json.loads((a.capture/'assessment.json').read_text())
for name,digest in parent['artifacts'].items():
 if sha(a.capture/name)!=digest:raise ValueError('Capture changed')
text=(a.capture/'bench.v').read_text();needle=' tv80n cpu('
if text.count(needle)!=1:raise ValueError('Unexpected CPU instantiation')
bench=a.out/'bench.v';bench.write_text(text.replace(needle,' tv80n #(.T2Write(1)) cpu('))
sources=[*sorted((ROOT/'third_party/cpu/tv80').glob('*.v')),BOARD/'chips.v',BOARD/'generated/controller.v',bench]
subprocess.run(['iverilog','-g2012','-s','firmware_tb','-o',str(a.out/'bench.vvp'),*map(str,sources)],check=True)
with (a.out/'hdl.txt').open('w') as f:subprocess.run(['vvp',str(a.out/'bench.vvp'),'+rom='+str((a.capture/'rom.hex').resolve())],stdout=f,check=True,timeout=300)
r=assess(parent['scenario'],parse(a.capture/'c.txt'),parse(a.out/'hdl.txt'))
r.update(qualified=False,profile='TV80 T2Write=1',sourceCaptureSha256=sha(a.capture/'assessment.json'),sourceCTraceSha256=sha(a.capture/'c.txt'),producerSha256=sha(Path(__file__)),hdlSha256=sha(a.out/'hdl.txt'),sources={str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else str(p):sha(p) for p in sources},boundary='Parameter sensitivity only. Earlier write assertion may change pulse width and setup/hold; matching serial edges does not establish U880 pin timing, read phases or electrical qualification.')
(a.out/'assessment.json').write_text(json.dumps(r,indent=2)+'\n');print(r['functionalAgreement'],r['rawCycleAgreement'])
