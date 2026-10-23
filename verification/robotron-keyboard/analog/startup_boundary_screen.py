#!/usr/bin/env python3
"""Fail-fast clock prerequisite from a prepared closed-board deck, before firmware acceptance."""
import argparse,json,math,re,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from ngspice_runtime import identify,verify
from failure_evidence import solver_diagnostic
from clock_voltage import inspect as voltage
from clock_timing import inspect as timing
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--duration-us',type=float,default=500);p.add_argument('--ngspice',required=True);p.add_argument('--spinit',type=Path,required=True);a=p.parse_args()
 if not math.isfinite(a.duration_us) or not 0<a.duration_us<=1000:p.error('Screen duration must be in (0, 1000] us')
 a.out.mkdir(parents=True,exist_ok=False);report={'completed':False,'passed':False,'qualified':False,'scope':__doc__,'durationSeconds':a.duration_us*1e-6,
 'boundary':'Bounded startup clock screen only. Reset release, firmware execution, scenario coverage and supply recovery are not accepted by this screen.',
 'sources':{n:sha(HERE/n) for n in ('startup_boundary_screen.py','clock_voltage.py','clock_timing.py','cpu_clock_limits.json','failure_evidence.py','ngspice_runtime.py')}}
 try:
  original=(a.prepared/'boot.cir').read_text();match=re.search(r'^\.tran ([\d.]+)n ([\d.e+-]+) 0$',original,re.M)
  if not match or float(match[2])<=report['durationSeconds']:raise ValueError('Expected longer startup-inclusive deck')
  report['stepNs']=float(match[1]);report['sourceDeckSha256']=sha(a.prepared/'boot.cir')
  deck=original[:match.start()]+f'.tran {match[1]}n {report["durationSeconds"]:.17g} 0'+original[match.end():]
  # Retain the complete circuit. Only observation duration and output selection change.
  deck=re.sub(r'^wrdata bus-trace.txt.*\n','',deck,flags=re.M)
  (a.out/'boot.cir').write_text(deck);report['deckSha256']=sha(a.out/'boot.cir')
  names=['boot.vvp','s600.hex']+re.findall(r'^\.include (\S+)$',original,re.M)
  report['copiedInputs']={}
  for name in names:
   if Path(name).name!=name:raise ValueError('Expected local prepared input')
   shutil.copyfile(a.prepared/name,a.out/name);report['copiedInputs'][name]=sha(a.out/name)
  runtime,env=identify(a.ngspice,a.spinit);report['runtime']=runtime
  result=subprocess.run([a.ngspice,'-n','-b','boot.cir'],cwd=a.out,env=env,capture_output=True,text=True,timeout=180)
  log=result.stdout+result.stderr;(a.out/'ngspice.log').write_text(log);report['exitCode']=result.returncode
  verify(runtime)
  if result.returncode or solver_diagnostic(log):raise ValueError('Startup screen simulator diagnostics')
  rows=(a.out/'trace.txt').read_text().splitlines();first=float(rows[1].split()[0]);last=float(rows[-1].split()[0])
  if first>1e-12 or abs(last-report['durationSeconds'])>1e-12:raise ValueError('Incomplete startup screen waveform')
  report['clockVoltage']=voltage(a.out/'trace.txt',a.out/'supply-trace.txt',diagnostic_columns=2)
  report['clockTiming']=timing(a.out/'trace.txt',a.out/'supply-trace.txt',report['stepNs'],diagnostic_columns=2)
  v=report['clockVoltage'];c=v['cycles']
  report['passed']=bool(c['assessedWithinSupplyRange'] and not c['missingHighExcursion'] and not c['missingLowExcursion'] and not v['inputRangeViolations'] and report['clockTiming']['passed'])
  report['completed']=True
  report['artifacts']={n:sha(a.out/n) for n in ('trace.txt','supply-trace.txt','ngspice.log')}
 except Exception as e:report['error']=str(e);raise
 finally:(a.out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print(a.out/'assessment.json')
 if not report['passed']:raise SystemExit(1)
if __name__=='__main__':main()
