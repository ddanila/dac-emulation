#!/usr/bin/env python3
"""Run bounded live-feedback controls without accepting incomplete simulations."""
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
from ngspice_runtime import identify,verify
from eval_cache_benchmark import external_dependencies,verify_dependencies
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
from fixture_crossing_grid import add_crossings
from sampling_grid import add_sampling_grid
from network_trace import observe_network, PHYSICAL_SIGNALS
from io_scenario import load as load_scenario

def live_diagnostic(log):
 # Icarus can abort HDL initialization with SORRY while ngspice still exits zero.
 diagnostic=solver_diagnostic(log)
 unsupported=re.search(r'^.*SORRY:.*$',log,re.M)
 return diagnostic or (unsupported.group(0) if unsupported else None)

def reduce_matrix(deck):
 """Diagnostic empty-matrix boundary; this is not equivalent full-board evidence."""
 start=deck.index('R1_2 ');end=deck.index('R10.1 ',start)
 deck=deck[:start]+'.model D_NOMINAL D(IS=1e-14 N=1)\n'+'\n'.join(f'Vmatrix_boundary{i} n_SENSE{i} 0 0' for i in range(8))+'\n'+deck[end:]
 return '\n'.join(l for l in deck.splitlines() if not l.startswith('Vcontact'))

def tighten_tolerances(deck, scale, components):
 if not 0<scale<=1 or not components or len(set(components))!=len(components) or set(components)-{'reltol','vntol','abstol'}:
  raise ValueError('Expected a tightening factor and distinct tolerance components')
 for key in components:
  deck,count=re.subn(r'('+key+r'=)([0-9.eE+-]+)',lambda m:m[1]+format(float(m[2])*scale,'.17g'),deck,flags=re.I)
  if count!=1:raise ValueError('Expected one '+key)
 return deck

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('prepared','spinit','out'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--halt-ns',type=float);p.add_argument('--dac-state-audit',action='store_true');p.add_argument('--tolerance-components',nargs='+',choices=('reltol','vntol','abstol'),default=['reltol','vntol','abstol']);p.add_argument('--sampling-grid',type=Path);p.add_argument('--all-saved-network',action='store_true');p.add_argument('--physical-driver-trace',action='store_true');p.add_argument('--adc-crossings',action='store_true');p.add_argument('--network-trace',action='store_true');p.add_argument('--passive-assembly',action='store_true');p.add_argument('--inductor-monitor',action='store_true');p.add_argument('--cap-paired-rhs',action='store_true');p.add_argument('--conservative-cap',action='store_true');p.add_argument('--switch-audit',action='store_true');p.add_argument('--method',choices=('trap','gear'));p.add_argument('--mpfr-start-ns',type=float);p.add_argument('--fixture-crossings-ps',type=float,choices=(1,.5,.25));p.add_argument('--ngspice',required=True);p.add_argument('--audit',action='store_true');p.add_argument('--mpfr-transition',choices=('256','512'));p.add_argument('--state-audit',action='store_true');p.add_argument('--dac-corners',action='store_true');p.add_argument('--reduce-matrix',action='store_true');p.add_argument('--stop-ns',type=float);p.add_argument('--tolerance-scale',type=float,default=1);p.add_argument('--step-ns',type=float,default=25);p.add_argument('--timeout',type=float,default=60);a=p.parse_args()
 if a.step_ns<=0 or a.timeout<=0 or not 0<a.tolerance_scale<=1 or (a.stop_ns is not None and a.stop_ns<=0):p.error('Step and timeout must be positive')
 if a.mpfr_start_ns is not None and (not a.mpfr_transition or not 0<=a.mpfr_start_ns<1e12):p.error('MPFR start requires MPFR and a finite nonnegative start')
 if a.conservative_cap and a.cap_paired_rhs:p.error("Choose one capacitor correction")
 if (a.conservative_cap or a.cap_paired_rhs) and (not a.mpfr_transition or a.method=='gear'):p.error('Conservative capacitor experiment requires MPFR and trapezoidal integration')
 if a.passive_assembly and not a.conservative_cap:p.error('Passive addition experiment requires exact capacitor correction')
 generator_sha=sha(Path(__file__))
 runtime,env=identify(a.ngspice,a.spinit);env['ROBOTRON_EVAL_CACHE']='off'
 dependencies=external_dependencies(a.prepared,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
 for key in ('ROBOTRON_DAC_STATE_AUDIT','ROBOTRON_LIVE_AUDIT','ROBOTRON_LIVE_EVENTS','ROBOTRON_DAC_BREAKPOINTS','ROBOTRON_STATE_AUDIT','ROBOTRON_MPFR_BITS','ROBOTRON_MPFR_TRANSITION_ONLY','ROBOTRON_MPFR_START','ROBOTRON_SWITCH_AUDIT','ROBOTRON_CAP_ASSEMBLY','ROBOTRON_INDUCTOR_MONITOR','ROBOTRON_POSTCAP_ASSEMBLY','ROBOTRON_ADC_CROSSINGS'):env.pop(key,None)
 if a.adc_crossings:env['ROBOTRON_ADC_CROSSINGS']='1'
 if a.audit:env.update(ROBOTRON_LIVE_AUDIT='1',ROBOTRON_LIVE_EVENTS='1')
 if a.mpfr_transition:env.update(ROBOTRON_MPFR_BITS=a.mpfr_transition,ROBOTRON_MPFR_TRANSITION_ONLY='1')
 if a.mpfr_start_ns is not None:env['ROBOTRON_MPFR_START']=format(a.mpfr_start_ns*1e-9,'.17g')
 if a.conservative_cap:env['ROBOTRON_CAP_ASSEMBLY']='exact'
 if a.cap_paired_rhs:env['ROBOTRON_CAP_ASSEMBLY']='paired-rhs'
 if a.passive_assembly:env['ROBOTRON_POSTCAP_ASSEMBLY']='exact'
 if a.inductor_monitor:env['ROBOTRON_INDUCTOR_MONITOR']='1'
 if a.switch_audit:env['ROBOTRON_SWITCH_AUDIT']='1'
 if a.state_audit:env['ROBOTRON_STATE_AUDIT']='1'
 if a.dac_state_audit:env['ROBOTRON_DAC_STATE_AUDIT']='1'
 if a.dac_corners:env['ROBOTRON_DAC_BREAKPOINTS']='1'
 a.out.mkdir(parents=True,exist_ok=False)
 for name in ('io.vvp','s600.hex'):shutil.copyfile(a.prepared/name,a.out/name)
 deck=(a.prepared/'io.cir').read_text()
 if a.physical_driver_trace:
  if not a.network_trace or 'Xdata n_D0 n_TA_DATEN driver_vp 0 TTL7406_DYNAMIC' not in deck or 'Xclock n_WR_N n_TA_TAKT driver_vp 0 TTL7406_DYNAMIC' not in deck:raise ValueError('Physical trace requires direct dynamic drivers and network-trace')
  deck=observe_network(deck,PHYSICAL_SIGNALS)
 elif a.network_trace:deck=observe_network(deck)
 observation_signals=None
 if a.all_saved_network:
  if not a.network_trace:raise ValueError('All saved observations require network trace')
  saves=re.findall(r'^.save (.*)$',deck,re.M)
  if len(saves)!=1:raise ValueError('Expected one save directive')
  observation_signals=list(dict.fromkeys(saves[0].split()))
  deck,count=re.subn(r'^wrdata network_witness.txt .*$', 'wrdata network_witness.txt '+' '.join(observation_signals),deck,flags=re.M)
  if count!=1:raise ValueError('Expected one network writer')
 if a.method:deck=deck.replace('.control',f'.options method={a.method} maxord=2\n.control',1)
 if a.reduce_matrix:deck=reduce_matrix(deck)
 if a.fixture_crossings_ps:
  scenario_path=a.prepared/'scenario.json'
  deck=add_crossings(deck,a.fixture_crossings_ps,load_scenario(scenario_path) if scenario_path.exists() else None, stop_ns=a.stop_ns)
 deck,count=re.subn(r'^\.tran\s+\S+',f'.tran {a.step_ns:g}n',deck,flags=re.M)
 if count!=1:raise ValueError('Expected one transient')
 if a.stop_ns is not None:
  deck=re.sub(r'^(\.tran\s+\S+)\s+\S+',lambda m:m[1]+f' {a.stop_ns:g}n',deck,flags=re.M)
 sampling_hash=None
 if a.sampling_grid:
  shutil.copyfile(a.sampling_grid,a.out/'sampling-grid.json')
  sampling_hash=sha(a.out/'sampling-grid.json')
  grid=json.loads((a.out/'sampling-grid.json').read_text())
  deck=add_sampling_grid(deck,grid['timesSeconds'],a.stop_ns)
 if a.tolerance_scale!=1:deck=tighten_tolerances(deck,a.tolerance_scale,a.tolerance_components)

 if a.halt_ns is not None:
  from diagnostic_halt import add_halt
  deck=add_halt(deck,a.halt_ns,a.stop_ns)
 (a.out/'io.cir').write_text(deck);start=time.monotonic();code=None;timedout=False
 with (a.out/'ngspice.log').open('w') as log:
  try:code=subprocess.run([a.ngspice,'-n','-b','io.cir'],cwd=a.out,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout).returncode
  except subprocess.TimeoutExpired:timedout=True
 verify(runtime)
 verify_dependencies(dependencies)
 logtext=(a.out/'ngspice.log').read_text()
 if a.mpfr_transition and 'MPFR_DIAGNOSTIC bits='+a.mpfr_transition not in logtext:raise ValueError('Runtime did not acknowledge MPFR request')
 if a.state_audit and 'STATE_AUDIT trial ' not in logtext:raise ValueError('Runtime did not capture state audit')
 if a.conservative_cap and 'CAP_ASSEMBLY mode=1' not in logtext:raise ValueError('Runtime did not acknowledge exact capacitor mode')
 if a.cap_paired_rhs and 'CAP_ASSEMBLY mode=2' not in logtext:raise ValueError('Runtime did not acknowledge paired RHS mode')
 if a.passive_assembly and 'POSTCAP_ASSEMBLY mode=1' not in logtext:raise ValueError('Runtime did not acknowledge passive assembly mode')
 if a.dac_state_audit and 'DAC_STATE time=' not in logtext:raise ValueError('Missing DAC state audit')
 result={'haltNs':a.halt_ns,'dacStateAudit':a.dac_state_audit,'toleranceComponents':a.tolerance_components,'samplingGridSha256':sampling_hash,'externalDependencies':dependencies,'observationSignals':observation_signals,'exitCode':code,'timedOut':timedout,'elapsedSeconds':time.monotonic()-start,'runtime':runtime,'enabled':a.dac_corners,'adcCrossings':a.adc_crossings,'audit':a.audit,'stateAudit':a.state_audit,'switchAudit':a.switch_audit,'conservativeCap':a.conservative_cap,'capPairedRhs':a.cap_paired_rhs,'inductorMonitor':a.inductor_monitor,'passiveAssembly':a.passive_assembly,'physicalDriverTrace':a.physical_driver_trace,'networkTrace':a.network_trace,'mpfrTransitionBits':a.mpfr_transition,'mpfrStartNs':a.mpfr_start_ns,'matrixBoundarySubstitution':a.reduce_matrix,'stepNs':a.step_ns,'stopNs':a.stop_ns,'fixtureCrossingGuardPs':a.fixture_crossings_ps,'toleranceScale':a.tolerance_scale,'qualified':False,'method':a.method or 'trap','solverDiagnostic':live_diagnostic(logtext),'sourceDeckSha256':sha(a.prepared/'io.cir'),'deckSha256':sha(a.out/'io.cir'),'inputs':{n:sha(a.out/n) for n in ('io.vvp','s600.hex')},'generatorSha256':generator_sha}
 (a.out/'run.json').write_text(json.dumps(result,indent=2)+'\n');print(a.out/'run.json')
if __name__=='__main__':main()
