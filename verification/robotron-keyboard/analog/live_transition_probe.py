#!/usr/bin/env python3
"""Run bounded live-feedback controls without accepting incomplete simulations."""
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
from ngspice_runtime import identify,verify
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic

def reduce_matrix(deck):
 """Diagnostic empty-matrix boundary; this is not equivalent full-board evidence."""
 start=deck.index('R1_2 ');end=deck.index('R10.1 ',start)
 deck=deck[:start]+'.model D_NOMINAL D(IS=1e-14 N=1)\n'+'\n'.join(f'Vmatrix_boundary{i} n_SENSE{i} 0 0' for i in range(8))+'\n'+deck[end:]
 return '\n'.join(l for l in deck.splitlines() if not l.startswith('Vcontact'))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('prepared','spinit','out'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--ngspice',required=True);p.add_argument('--audit',action='store_true');p.add_argument('--dac-corners',action='store_true');p.add_argument('--reduce-matrix',action='store_true');p.add_argument('--step-ns',type=float,default=25);p.add_argument('--timeout',type=float,default=60);a=p.parse_args()
 if a.step_ns<=0 or a.timeout<=0:p.error('Step and timeout must be positive')
 runtime,env=identify(a.ngspice,a.spinit);env['ROBOTRON_EVAL_CACHE']='off'
 for key in ('ROBOTRON_LIVE_AUDIT','ROBOTRON_LIVE_EVENTS','ROBOTRON_DAC_BREAKPOINTS'):env.pop(key,None)
 if a.audit:env.update(ROBOTRON_LIVE_AUDIT='1',ROBOTRON_LIVE_EVENTS='1')
 if a.dac_corners:env['ROBOTRON_DAC_BREAKPOINTS']='1'
 a.out.mkdir(parents=True,exist_ok=False)
 for name in ('io.vvp','s600.hex'):shutil.copyfile(a.prepared/name,a.out/name)
 deck=(a.prepared/'io.cir').read_text()
 if a.reduce_matrix:deck=reduce_matrix(deck)
 deck,count=re.subn(r'^\.tran\s+\S+',f'.tran {a.step_ns:g}n',deck,flags=re.M)
 if count!=1:raise ValueError('Expected one transient')
 (a.out/'io.cir').write_text(deck);start=time.monotonic();code=None;timedout=False
 with (a.out/'ngspice.log').open('w') as log:
  try:code=subprocess.run([a.ngspice,'-n','-b','io.cir'],cwd=a.out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout).returncode
  except subprocess.TimeoutExpired:timedout=True
 verify(runtime)
 result={'exitCode':code,'timedOut':timedout,'elapsedSeconds':time.monotonic()-start,'runtime':runtime,'enabled':a.dac_corners,'audit':a.audit,'matrixBoundarySubstitution':a.reduce_matrix,'stepNs':a.step_ns,'qualified':False,'solverDiagnostic':solver_diagnostic((a.out/'ngspice.log').read_text()),'sourceDeckSha256':sha(a.prepared/'io.cir'),'deckSha256':sha(a.out/'io.cir'),'inputs':{n:sha(a.out/n) for n in ('io.vvp','s600.hex')},'generatorSha256':sha(Path(__file__))}
 (a.out/'run.json').write_text(json.dumps(result,indent=2)+'\n');print(a.out/'run.json')
if __name__=='__main__':main()
