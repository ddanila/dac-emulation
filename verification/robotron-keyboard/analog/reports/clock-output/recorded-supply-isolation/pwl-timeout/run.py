"""Run from the core repository root; diagnostic supply replay, not qualification."""
from pathlib import Path
import sys, json, hashlib, lzma, shutil, subprocess
ROOT=Path.cwd();HERE=ROOT/'verification/robotron-keyboard/analog';sys.path.insert(0,str(HERE))
from circuit import load
from oscillator_probe import wiring
from clock_convergence import compare_clocks
from failure_evidence import solver_diagnostic
OUT=ROOT/'build/keyboard-controller-analog/clock-supply-replay'
SOURCE=ROOT/'build/keyboard-controller-analog/coupled-clock-tight-refinement/coarse/diagnostic-trace.txt.xz'
ENGINE='/tmp/robotron-ngspice-switch/install/bin/ngspice-unpatched'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
report={'qualified':False,'scope':'Isolated schematic oscillator driven by the same prescribed board supply at both timesteps; no live HDL or supply feedback.', 'sourceCompressedSha256':sha(SOURCE),'runs':[]}
# Preserve printed supply samples exactly; reject ambiguous duplicate timestamps.
points=[];duplicates=0;raw_hash=hashlib.sha256()
with lzma.open(SOURCE,'rt') as f:
 header=next(f);raw_hash.update(header.encode());assert header.split()[1]=='v(n_p5V)'
 for line in f:
  raw_hash.update(line.encode());t,v=line.split()[:2]
  if points and float(t)==float(points[-1][0]):
   if float(v)!=float(points[-1][1]):raise ValueError('Conflicting supply values at one printed timestamp')
   duplicates+=1;continue
  if points and float(t)<float(points[-1][0]):raise ValueError('Supply time reversal')
  points.append((t,v))
assert float(points[0][0])==0 and abs(float(points[-1][0])-250e-6)<1e-12
report.update(sourceUncompressedSha256=raw_hash.hexdigest(),identicalDuplicateSamples=duplicates,
 sourceBoundary='Printed samples become a piecewise-linear ideal voltage source. This removes supply loading feedback and preserves the source trace rounding; it is not a physical supply model.')
include='Vreplay n_p5V 0 PWL(\n'+''.join('+ '+t+' '+v+'\n' for t,v in points)+'+ )\n'
(OUT/'supply.inc').write_text(include);report['supplyIncludeSha256']=sha(OUT/'supply.inc')
components,report['connectivitySha256']=load();lines,_,_,source,cpu=wiring(components)
try:
 for label,step in (('coarse',.25),('fine',.125)):
  out=OUT/label;out.mkdir(exist_ok=True)
  shutil.copyfile(HERE/'ls_nand_pullup.cir',out/'ls_nand_pullup.cir')
  deck='Recorded-supply oscillator isolation\n.include ../supply.inc\n.include ls_nand_pullup.cir\n.options reltol=1e-6 vntol=1e-8 abstol=1e-14\n'+'\n'.join(lines)+f'\n.control\nset wr_singlescale\nset wr_vecnames\nset numdgt=17\ntran {step}n 250u\nwrdata trace.txt v({cpu})\nquit\n.endc\n.end\n'
  (out/'oscillator.cir').write_text(deck)
  with (out/'ngspice.log').open('w') as log:
   result=subprocess.run([ENGINE,'-n','-b','oscillator.cir'],cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=600)
  record={'stepNs':step,'exitCode':result.returncode,'deckSha256':sha(out/'oscillator.cir'),'logSha256':sha(out/'ngspice.log')};report['runs'].append(record)
  result.check_returncode();diagnostic=solver_diagnostic((out/'ngspice.log').read_text())
  if diagnostic:raise ValueError(diagnostic)
  record['traceSha256']=sha(out/'trace.txt')
  print(label,'completed',flush=True)
 report['clockPhase']=compare_clocks(OUT/'coarse/trace.txt',OUT/'fine/trace.txt',.25,.125,columns=2)
 report['completed']=True
except Exception as e:
 report.update(completed=False,error=str(e));raise
finally:
 (OUT/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
