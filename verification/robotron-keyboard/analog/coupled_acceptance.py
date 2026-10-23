#!/usr/bin/env python3
"""Run paired qualified-CPU electrical acceptance, stopping at failed prerequisites."""
import argparse,json,subprocess,sys
from pathlib import Path
from ttl7406_probe import sha
from ngspice_runtime import identify,verify
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('rom','bridge','spinit','out'):p.add_argument('--'+key,type=Path,required=True)
 p.add_argument('--ngspice',required=True);p.add_argument('--plan-only',action='store_true');p.add_argument('--reuse-single-press',type=Path,nargs=2,metavar=('COARSE','FINE'))
 a=p.parse_args();a.out.mkdir(parents=True,exist_ok=True)
 common=['--rom',str(a.rom.resolve()),'--bridge',str(a.bridge.resolve()),'--ngspice',a.ngspice,'--ngspice-spinit',str(a.spinit.resolve()),'--cpu-profile','qualified-digital','--electrical-bus','--bus-latch-pf','5','--bus-7406-pf','5','--minimum-breakpoint-fs','1','--compress-traces']
 jobs=[]
 for name in ('single-press','modifier','release-repress','reset','repeat','control','indicators'):
  scenario=HERE/'scenarios'/f'{name}.json';pair=[]
  for label,step in (('coarse','50'),('fine','25')):
   directory=a.out/name/label
   if name=='single-press' and a.reuse_single_press:directory=a.reuse_single_press[0 if label=='coarse' else 1]
   pair.append({'label':label,'directory':str(directory.resolve()),'status':'not-run','command':[sys.executable,str(HERE/'firmware_io_cosim.py'),*common,'--scenario',str(scenario),'--step-ns',step,'--timeout-seconds','21600','--out',str(directory.resolve())]})
  jobs.append({'name':name,'scope':'BR service fixture; onboard clock/reset excluded','scenarioSha256':sha(scenario),'status':'not-run','runs':pair})
 result={'qualified':False,'planOnly':a.plan_only,'jobs':jobs,'generatorSha256':sha(Path(__file__)),
 'assumptions':{'busLatchPf':5,'bus7406Pf':5,'scope':'Reference stress assumptions, not measured device capacitance'},
 'closedBoardAcceptance':{'status':'not-run','requires':['Service electrical bus/transport and refinement acceptance','Independent oscillator/driver/host model admission','Closed-board startup and contact scenarios with qualified CPU','Supply-dip recovery using explicit stimulus; CPU-side forced reset is not brownout evidence']},
 'boundary':'A passing service suite does not qualify onboard startup, supply recovery, calibrated device dynamics or specimen fidelity.'}
 receipt=a.out/'assessment.json'
 def save():receipt.write_text(json.dumps(result,indent=2)+'\n')
 save()
 if a.plan_only:return
 runtime,_=identify(a.ngspice,a.spinit);bridge=json.loads(a.bridge.read_text())
 for lib in bridge['libraries'].values():
  if sha(Path(lib['path']))!=lib['sha256']:raise ValueError('Changed bridge binary')
 blocked=False
 for job in jobs:
  if blocked:job['status']='blocked-by-service-prerequisite';continue
  for run in job['runs']:
   directory=Path(run['directory']);report_path=directory/'report.json'
   if not(job['name']=='single-press' and a.reuse_single_press):
    directory.mkdir(parents=True,exist_ok=True)
    if report_path.exists():raise ValueError('Refusing to overwrite existing acceptance run: '+str(directory))
    with (directory/'producer.log').open('w') as log:
     run['exitCode']=subprocess.run(run['command'],stdout=log,stderr=subprocess.STDOUT).returncode
   report=json.loads(report_path.read_text());assumptions=report['assumptions']
   verify(runtime)
   if report['ngspiceRuntime']!=runtime or report['bridge']!=bridge:raise ValueError('Acceptance runtime differs')
   expected_step=50 if run['label']=='coarse' else 25
   if assumptions['cpuProfile']!='qualified-digital' or assumptions['stepNs']!=expected_step or not assumptions['electricalBus'] or (assumptions['busLatchPf'],assumptions['bus7406Pf'])!=(5,5):raise ValueError('Acceptance inputs differ')
   if report['romSha256']!=sha(a.rom) or report['scenarioSha256']!=job['scenarioSha256']:raise ValueError('Acceptance ROM/scenario differs')
   run.update(status='passed' if report['passed'] else 'failed',reportSha256=sha(report_path),error=report.get('error'));save()
  if all(r['status']=='passed' for r in job['runs']):
   pair_out=a.out/job['name']/'qualification'
   code=subprocess.run([sys.executable,str(HERE/'qualify_io_pair.py'),*[r['directory'] for r in job['runs']],'--scenario',str(HERE/'scenarios'/f'{job["name"]}.json'),'--out',str(pair_out)]).returncode
   job['status']='passed' if code==0 else 'failed-refinement';job['pairReportSha256']=sha(pair_out/'qualification.json')
  else:job['status']='failed'
  blocked=job['status']!='passed';save()
 result['servicePassed']=all(j['status']=='passed' for j in jobs);save();print(receipt)
 if not result['servicePassed']:raise SystemExit(1)
if __name__=='__main__':main()
