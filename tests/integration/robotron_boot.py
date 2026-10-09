#!/usr/bin/env python3
"""Optional original-media smoke: never writes input files; no HDL."""
import argparse, hashlib, json, re, subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('rom',type=Path);p.add_argument('prom',type=Path);p.add_argument('disk',type=Path);p.add_argument('--report',type=Path);args=p.parse_args()
root=Path(__file__).resolve().parents[2]
inputs=[x.resolve() for x in (args.rom,args.prom,args.disk)]
identities={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs}
scenarios=[('directory','DIR\r',['A>DIR','SCP3','AUTOEXC']),('type','TYPE AUTOEXC.SUB\r',['MODCS COMMON0','FKEY']),('write','ERA AUTOEXC.BAK\rDIR AUTOEXC.*\r',['A>DIR AUTOEXC.*','AUTOEXC  SUB'])]
report={'inputs':identities,'cases':[]}
for name,keys,expected in scenarios:
 result=subprocess.run([root/'build/robotron-boot',*inputs,'40000000',keys,*(['--writable'] if name=='write' else [])],capture_output=True,text=True,check=True,timeout=10)
 for text in expected:assert text in result.stdout,(name,text,result.stdout,result.stderr)
 if name=='write':
  assert 'AUTOEXC  BAK' not in result.stdout
  assert re.search(r'writes=[1-9][0-9]*',result.stderr),result.stderr
 report['cases'].append({'name':name,'state':result.stderr.strip(),'screen_sha256':hashlib.sha256(result.stdout.encode()).hexdigest()})
 print('PASS Robotron',name,result.stderr.strip())
assert identities=={str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in inputs},'input media modified'
if args.report:args.report.write_text(json.dumps(report,indent=2)+'\n')
