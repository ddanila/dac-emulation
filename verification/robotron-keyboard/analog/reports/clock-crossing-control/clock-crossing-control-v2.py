from pathlib import Path
import sys,json,subprocess,hashlib,re,time,math
sys.path.insert(0,str(Path('verification/robotron-keyboard/analog').resolve()))
from ngspice_runtime import identify,verify
root=Path('build/keyboard-controller-analog/clock-crossing-control-v2').resolve();root.mkdir(exist_ok=False)
bridge_path=Path('build/keyboard-controller-analog/rollback-time-bridge-postreset/bridge.json');bridge=json.loads(bridge_path.read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for item in bridge['libraries'].values():assert sha(Path(item['path']))==item['sha256']
(root/'clock_echo.v').write_text('`timescale 1ns/1ps\nmodule clock_echo(input clk, output q); assign q=clk; endmodule\n')
subprocess.run(['iverilog','-g2012','-s','clock_echo','-o',str(root/'io.vvp'),str(root/'clock_echo.v')],check=True)
runtime,env=identify('/private/tmp/k7658-selectable-retry-runtime','/private/tmp/k7658-startup-fixes-v1/spinit')
for key in list(env):
 if key.startswith('ROBOTRON_'):del env[key]
env.update(ROBOTRON_HISTORY_INIT='on',ROBOTRON_STAGED_OUTPUT='on',ROBOTRON_HISTORY_STATE='off',ROBOTRON_ADC_TRACE='1')
paths={k:v['path'] for k,v in bridge['libraries'].items()};runs=[]
for enabled in (False,True):
 for step in (25,12.5,6.25):
  out=root/f'{"on" if enabled else "off"}-{step}';out.mkdir();(out/'io.vvp').write_bytes((root/'io.vvp').read_bytes())
  deck=f'''External clock ADC and bridge timing control
Vclock clock 0 PULSE(0 5 500n 1n 1n 499n 1u)
Ainput [clock] [clk] receiver
.model receiver adc_bridge(in_low=1.4 in_high=1.4)
Ahdl [clk] [q] hdl
.model hdl d_cosim simulation="{paths['shim']}" sim_args=["io.vvp"] delay=10n
+ lib_args=["{paths['libvvp']}" "{paths['vpi']}"]
Adac [q] [out] drive
.model drive dac_bridge(out_low=0 out_high=5 out_undef=2.5 t_rise=1n t_fall=1n)
Rload out 0 1k
.options reltol=1e-8 vntol=1e-9 abstol=1e-15 minbreak=1f trtol=.25
.save v(clock) v(out)
.tran {step}n 1.1091m
.control
set filetype=binary
run waveform.raw
quit
.endc
.end
'''
  (out/'probe.cir').write_text(deck);e=dict(env)
  if enabled:e['ROBOTRON_ADC_CROSSINGS']='1'
  start=time.monotonic()
  with (out/'ngspice.log').open('w') as log, (out/'stderr.log').open('w') as err:
   p=subprocess.run([runtime['executable']['path'],'-n','-b','probe.cir'],cwd=out,env=e,stdout=log,stderr=err,timeout=120)
  text=(out/'ngspice.log').read_text()+'\n'+(out/'stderr.log').read_text();assert p.returncode==0 and 'No. of Data Rows' in text
  assert not re.search(r'Error:|Warning:|timestep too small|SORRY:',text,re.I),text[-2000:]
  adc=[{'time':float.fromhex(t),'new':int(n)} for t,n in re.findall(r'ADC_CROSS time=(\S+) node=clock value=\S+ old=\d+ new=(\d+)',text)]
  outputs=[{'actual':float(a),'target':float(t),'base':float(b)} for a,t,b in re.findall(r'TIME_AUDIT output actual=(\S+) target=(\S+) base=(\S+) port=q',text)]
  assert [x['new'] for x in adc]==[0]+[state for _ in range(1109) for state in (1,0)]
  expected=[0]+[t for cycle in range(1109) for t in ((500.28+cycle*1000)*1e-9,(1000.72+cycle*1000)*1e-9)]
  errors=[abs(x['time']-t) for x,t in zip(adc,expected)]
  run={'enabled':enabled,'stepNs':step,'exitCode':p.returncode,'elapsedSeconds':time.monotonic()-start,'adcEvents':len(adc),'maximumAdcTimeErrorSeconds':max(errors),'lastAdc':adc[-1],'lastExpectedAdcTimeSeconds':expected[-1],'lastOutput':outputs[-1],'environment':{k:v for k,v in e.items() if k.startswith('ROBOTRON_')},'files':{f.name:sha(f) for f in out.iterdir() if f.is_file()}}
  (out/'run.json').write_text(json.dumps(run,indent=2)+'\n');runs.append(run);print({k:run[k] for k in ('enabled','stepNs','maximumAdcTimeErrorSeconds','lastAdc','lastOutput')},flush=True)
verify(runtime)
report={'completed':True,'qualified':False,'scope':'Analytic external-clock crossing control at the same absolute-time scale, ADC thresholds and delay as the board fixture. No CPU, nonlinear board, state rollback or convergence qualification.','runtime':runtime,'bridge':bridge,'runs':runs,'scriptSha256':sha(Path(__file__))}
(root/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
