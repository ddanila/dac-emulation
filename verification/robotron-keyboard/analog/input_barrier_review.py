#!/usr/bin/env python3
"""Retain and recheck the scoped input-boundary scheduler regression evidence."""
import argparse,hashlib,json,lzma,re,shutil
from pathlib import Path
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
from trace_io import open_binary
HERE=Path(__file__).resolve().parent
SOURCES=('input_barrier_review.py','build_cosim_input_barrier.py','test_cosim_input_barrier.py','fixtures/cosim_order_harness.c','engine-patches/cosim-input-barrier.patch','coupled_acceptance.py','startup_boundary_screen.py','bridge_probe.py','ngspice_runtime.py','failure_evidence.py','clock_voltage.py','clock_timing.py','cpu_clock_limits.json')

def examine(root):
 build=json.loads((root/'build.json').read_text());transport=json.loads((root/'transport.json').read_text());runs={}
 if build['patches']['cosim-input-barrier.patch']!=sha(HERE/'engine-patches/cosim-input-barrier.patch'):raise ValueError('Stale scheduling patch')
 for name,step in (('coarse',50),('fine',25)):
  folder=root/name;r=json.loads((folder/'report.json').read_text());log=lzma.decompress((folder/'ngspice.log.xz').read_bytes()).decode()
  if hashlib.sha256(log.encode()).hexdigest()!=r['failureArtifacts']['ngspice.log']['sha256']:raise ValueError('Changed producer log')
  if r['assumptions']['stepNs']!=step or r['assumptions']['cpuProfile']!='qualified-digital' or not r['productionReference']:raise ValueError('Wrong CPU/step')
  models=r['ngspiceRuntime']['codeModels']
  if not any(m['sha256']==build['outputs']['digital.cm'] for m in models):raise ValueError('Capture did not use reviewed code model')
  evidence=json.loads((folder/'waveform-review.json').read_text());failure=r['busFailure'];row=evidence['busWitness']
  if row[0]!=failure['traceTimeSeconds'] or row[2]!=failure['volts'] or row[-1]!=failure['maximumVolts']:raise ValueError('Bus witness does not match failure')
  if failure['signal']!='D1' or not row[2]>row[-1]:raise ValueError('No retained supply-relative failure')
  for waveform,review in evidence['waveforms'].items():
   if review['firstSeconds']>1e-12 or abs(review['lastSeconds']-.03)>1e-12:raise ValueError('Incomplete capture')
   key='busTraceSha256' if waveform=='bus-trace.txt' else None
   if key and r[key]!=review['sha256']:raise ValueError('Trace receipt differs')
   if r['compressedWaveforms'][waveform]['sha256']!=review['sha256']:raise ValueError('Compression receipt differs')
  runs[name]={'captureCompleted':True,'solverDiagnostics':solver_diagnostic(log),'producerPassed':r['passed'],'error':r.get('error'),'busExcessVolts':row[2]-row[-1],'readTimePs':failure['readTimePs'],'reportSha256':sha(folder/'report.json')}
 a=json.loads((root/'coarse/report.json').read_text());b=json.loads((root/'fine/report.json').read_text())
 for key in ('sources','bridge','ngspiceRuntime','cpuModel','romSha256','scenarioSha256'):
  if a[key]!=b[key]:raise ValueError('Refinement inputs differ: '+key)
 def hdl(r):
  result={Path(k).name:v for k,v in r['hdlSha256'].items()}
  if len(result)!=len(r['hdlSha256']):raise ValueError('Ambiguous HDL names')
  return result
 if hdl(a)!=hdl(b):raise ValueError('Refinement HDL differs')
 if not any(m['sha256']==build['outputs']['digital.cm'] for m in transport['ngspiceRuntime']['codeModels']):raise ValueError('Transport runtime differs')
 aa=dict(a['assumptions']);bb=dict(b['assumptions']);aa.pop('stepNs');bb.pop('stepNs')
 if aa!=bb:raise ValueError('Refinement circuit assumptions differ')
 suite=json.loads((root/'service-acceptance.json').read_text())
 if suite['servicePassed'] or suite['jobs'][0]['status']!='failed' or any(j['status']!='blocked-by-service-prerequisite' for j in suite['jobs'][1:]):raise ValueError('Acceptance gate misrepresented')
 startup=json.loads((root/'startup/report.json').read_text())
 if startup['passed'] or 'timed out' not in startup.get('error',''):raise ValueError('Expected incomplete full startup')
 screen=json.loads((root/'startup-screen/assessment.json').read_text())
 if not screen['completed'] or screen['passed']:raise ValueError('Unexpected early startup result')
 from clock_voltage import inspect as voltage
 from clock_timing import inspect as timing
 folder=root/'startup-screen'
 if voltage(folder/'trace.txt',folder/'supply-trace.txt',diagnostic_columns=2)!=screen['clockVoltage']:raise ValueError('Startup voltage review differs')
 if timing(folder/'trace.txt',folder/'supply-trace.txt',screen['stepNs'],diagnostic_columns=2)!=screen['clockTiming']:raise ValueError('Startup timing review differs')
 return {'completed':True,'qualified':False,'orderingRegressionPassed':bool(transport['passed'] and all(not x['solverDiagnostics'] for x in runs.values())),
 'scope':'Input-driven qualified-CPU single-press service, matched 50/25 ns steps, plus original transport probe. Not a general rollback solution for arbitrary autonomous HDL events or multiple irreversible clients.',
 'runs':runs,'transportPassed':transport['passed'],'serviceAcceptancePassed':False,
 'startup':{'completed':False,'reason':'Full closed-board run timed out; bounded early screen has no rated-supply samples and cannot qualify CPU clock behavior.','earlyRatedSupplySamples':screen['clockVoltage']['validSupplySamples']},
 'remaining':['Resolve the supply-relative bus-voltage gate with convergence and model evidence; no limit was relaxed','Complete service scenario/refinement gates before full-board acceptance','Complete onboard startup, independent device dynamics and supply recovery'],
 'sources':{n:sha(HERE/n) for n in SOURCES}}

def retain(a):
 a.out.mkdir(parents=True,exist_ok=False)
 for name,source in [('coarse',a.coarse),('fine',a.fine)]:
  folder=a.out/name;folder.mkdir()
  r=json.loads((source/'report.json').read_text())
  for n in ('report.json','run-inputs.json','io.cir','controller_analog.v','reference.log','scenario.json'):shutil.copyfile(source/n,folder/n)
  (folder/'ngspice.log.xz').write_bytes(lzma.compress((source/'ngspice.log').read_bytes()))
  review={'waveforms':{},'busWitness':None}
  for n in ('trace.txt','bus-trace.txt'):
   expected=r['failureArtifacts'][n+'.xz']['sha256']
   if sha(source/(n+'.xz'))!=expected:raise ValueError('Changed compressed waveform')
   digest=hashlib.sha256();first=None;last=None;count=0
   with open_binary(source/n) as stream:
    header=stream.readline();digest.update(header)
    for line in stream:
     digest.update(line);count+=1
     if first is None:first=float(line.split()[0])
     last=line
     if n=='bus-trace.txt' and review['busWitness'] is None:
      # The failed read is early; stop parsing rows once its exact witness is found.
      fields=line.split()
      if float(fields[0])==r['busFailure']['traceTimeSeconds']:review['busWitness']=list(map(float,fields))
   review['waveforms'][n]={'sha256':digest.hexdigest(),'compressedSha256':expected,'rows':count,'firstSeconds':first,'lastSeconds':float(last.split()[0]),'localCapture':str((source/(n+'.xz')).resolve())}
  (folder/'waveform-review.json').write_text(json.dumps(review,indent=2)+'\n')
 for source,name in [(a.build,'build.json'),(a.transport,'transport.json'),(a.suite,'service-acceptance.json')]:shutil.copyfile(source,a.out/name)
 for label,source in [('startup',a.startup),('startup-screen',a.screen)]:
  folder=a.out/label;folder.mkdir()
  names=('report.json','run-inputs.json','boot.cir') if label=='startup' else ('assessment.json','boot.cir')
  for n in names:shutil.copyfile(source/n,folder/n)
  (folder/'ngspice.log.xz').write_bytes(lzma.compress((source/'ngspice.log').read_bytes()))
  if label=='startup-screen':
   for n in ('trace.txt','supply-trace.txt'):(folder/(n+'.xz')).write_bytes(lzma.compress((source/n).read_bytes()))
 assessment=examine(a.out);(a.out/'assessment.json').write_text(json.dumps(assessment,indent=2)+'\n')
 manifest={str(p.relative_to(a.out)):sha(p) for p in sorted(a.out.rglob('*')) if p.is_file()}
 (a.out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--verify',action='store_true');p.add_argument('--out',type=Path,required=True)
 for name in ('coarse','fine','build','transport','suite','startup','screen'):p.add_argument('--'+name,type=Path)
 a=p.parse_args()
 if a.verify:
  manifest=json.loads((a.out/'manifest.json').read_text())
  for n,digest in manifest.items():
   if sha(a.out/n)!=digest:raise ValueError('Changed retained file: '+n)
  if examine(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Stale assessment')
 else:
  if any(getattr(a,n) is None for n in ('coarse','fine','build','transport','suite','startup','screen')):p.error('All capture paths are required for retention')
  retain(a)
 print('Input-boundary regression verified; electrical and full-board acceptance remain open.')
if __name__=='__main__':main()
