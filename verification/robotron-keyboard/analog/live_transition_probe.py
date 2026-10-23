#!/usr/bin/env python3
"""Run bounded live-feedback controls without accepting incomplete simulations."""
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
from ngspice_runtime import identify,verify
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
from fixture_crossing_grid import add_crossings

def reduce_matrix(deck):
 """Diagnostic empty-matrix boundary; this is not equivalent full-board evidence."""
 start=deck.index('R1_2 ');end=deck.index('R10.1 ',start)
 deck=deck[:start]+'.model D_NOMINAL D(IS=1e-14 N=1)\n'+'\n'.join(f'Vmatrix_boundary{i} n_SENSE{i} 0 0' for i in range(8))+'\n'+deck[end:]
 return '\n'.join(l for l in deck.splitlines() if not l.startswith('Vcontact'))

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('prepared','spinit','out'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--switch-audit',action='store_true');p.add_argument('--method',choices=('trap','gear'));p.add_argument('--mpfr-start-ns',type=float);p.add_argument('--fixture-crossings-ps',type=float,choices=(1,.5));p.add_argument('--ngspice',required=True);p.add_argument('--audit',action='store_true');p.add_argument('--mpfr-transition',choices=('256','512'));p.add_argument('--state-audit',action='store_true');p.add_argument('--dac-corners',action='store_true');p.add_argument('--reduce-matrix',action='store_true');p.add_argument('--stop-ns',type=float);p.add_argument('--tolerance-scale',type=float,default=1);p.add_argument('--step-ns',type=float,default=25);p.add_argument('--timeout',type=float,default=60);a=p.parse_args()
 if a.step_ns<=0 or a.timeout<=0 or not 0<a.tolerance_scale<=1 or (a.stop_ns is not None and a.stop_ns<=0):p.error('Step and timeout must be positive')
 if a.mpfr_start_ns is not None and (not a.mpfr_transition or not 0<=a.mpfr_start_ns<1e12):p.error('MPFR start requires MPFR and a finite nonnegative start')
 generator_sha=sha(Path(__file__))
 runtime,env=identify(a.ngspice,a.spinit);env['ROBOTRON_EVAL_CACHE']='off'
 for key in ('ROBOTRON_LIVE_AUDIT','ROBOTRON_LIVE_EVENTS','ROBOTRON_DAC_BREAKPOINTS','ROBOTRON_STATE_AUDIT','ROBOTRON_MPFR_BITS','ROBOTRON_MPFR_TRANSITION_ONLY','ROBOTRON_MPFR_START','ROBOTRON_SWITCH_AUDIT'):env.pop(key,None)
 if a.audit:env.update(ROBOTRON_LIVE_AUDIT='1',ROBOTRON_LIVE_EVENTS='1')
 if a.mpfr_transition:env.update(ROBOTRON_MPFR_BITS=a.mpfr_transition,ROBOTRON_MPFR_TRANSITION_ONLY='1')
 if a.mpfr_start_ns is not None:env['ROBOTRON_MPFR_START']=format(a.mpfr_start_ns*1e-9,'.17g')
 if a.switch_audit:env['ROBOTRON_SWITCH_AUDIT']='1'
 if a.state_audit:env['ROBOTRON_STATE_AUDIT']='1'
 if a.dac_corners:env['ROBOTRON_DAC_BREAKPOINTS']='1'
 a.out.mkdir(parents=True,exist_ok=False)
 for name in ('io.vvp','s600.hex'):shutil.copyfile(a.prepared/name,a.out/name)
 deck=(a.prepared/'io.cir').read_text()
 if a.method:deck=deck.replace('.control',f'.options method={a.method} maxord=2\n.control',1)
 if a.reduce_matrix:deck=reduce_matrix(deck)
 if a.fixture_crossings_ps:deck=add_crossings(deck,a.fixture_crossings_ps)
 deck,count=re.subn(r'^\.tran\s+\S+',f'.tran {a.step_ns:g}n',deck,flags=re.M)
 if count!=1:raise ValueError('Expected one transient')
 if a.stop_ns is not None:
  deck=re.sub(r'^(\.tran\s+\S+)\s+\S+',lambda m:m[1]+f' {a.stop_ns:g}n',deck,flags=re.M)
 if a.tolerance_scale!=1:
  for key in ('reltol','vntol','abstol'):
   deck,count=re.subn(r'('+key+r'=)([0-9.eE+-]+)',lambda m:m[1]+format(float(m[2])*a.tolerance_scale,'.17g'),deck,flags=re.I)
   if count!=1:raise ValueError('Expected one '+key)

 (a.out/'io.cir').write_text(deck);start=time.monotonic();code=None;timedout=False
 with (a.out/'ngspice.log').open('w') as log:
  try:code=subprocess.run([a.ngspice,'-n','-b','io.cir'],cwd=a.out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout).returncode
  except subprocess.TimeoutExpired:timedout=True
 verify(runtime)
 logtext=(a.out/'ngspice.log').read_text()
 if a.mpfr_transition and 'MPFR_DIAGNOSTIC bits='+a.mpfr_transition not in logtext:raise ValueError('Runtime did not acknowledge MPFR request')
 if a.state_audit and 'STATE_AUDIT trial ' not in logtext:raise ValueError('Runtime did not capture state audit')
 result={'exitCode':code,'timedOut':timedout,'elapsedSeconds':time.monotonic()-start,'runtime':runtime,'enabled':a.dac_corners,'audit':a.audit,'stateAudit':a.state_audit,'switchAudit':a.switch_audit,'mpfrTransitionBits':a.mpfr_transition,'mpfrStartNs':a.mpfr_start_ns,'matrixBoundarySubstitution':a.reduce_matrix,'stepNs':a.step_ns,'stopNs':a.stop_ns,'fixtureCrossingGuardPs':a.fixture_crossings_ps,'toleranceScale':a.tolerance_scale,'qualified':False,'method':a.method or 'trap','solverDiagnostic':solver_diagnostic((a.out/'ngspice.log').read_text()),'sourceDeckSha256':sha(a.prepared/'io.cir'),'deckSha256':sha(a.out/'io.cir'),'inputs':{n:sha(a.out/n) for n in ('io.vvp','s600.hex')},'generatorSha256':generator_sha}
 (a.out/'run.json').write_text(json.dumps(result,indent=2)+'\n');print(a.out/'run.json')
if __name__=='__main__':main()
