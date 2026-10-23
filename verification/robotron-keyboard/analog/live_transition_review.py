#!/usr/bin/env python3
"""Retain and verify bounded live-transition diagnostics, never full-board acceptance."""
import argparse,json,lzma,re,shutil
from pathlib import Path
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic
from bus_transition_review import extent,stop_time
HERE=Path(__file__).resolve().parent
CASES={'control':'live-formal-control','audit':'live-formal-audit','corners-25':'live-formal-25','corners-50':'live-formal-50','corners-12':'live-formal-12',
       'reduced':'live-feedback-reduction/reduced','recorded-grid':'live-grid-controls/recorded-grid','ramp-endpoints':'live-grid-controls/ramp-endpoints','ramp-substeps':'live-grid-controls/ramp-substeps'}

def audit_stats(log):
 solvers=[];rejections=[];devices=[];adc=[]
 for line in log.splitlines():
  if 'ADC_LIVE ' in line:adc.append(line)
  if 'TRUNC_AUDIT device ' in line:devices.append(dict(re.findall(r'(\w+)=([^ ]+)',line)))
  if 'TRUNC_AUDIT solver ' in line:
   values=dict(re.findall(r'(\w+)=([^ ]+)',line));solvers.append(int(values['result']))
  if 'TRUNC_AUDIT step ' in line:
   values=dict(re.findall(r'(\w+)=([^ ]+)',line));delta=float.fromhex(values['delta']);proposed=float.fromhex(values['proposed'])
   if proposed<.9*delta:rejections.append({'timeSeconds':float.fromhex(values['time']),'trialStepSeconds':delta,'proposedStepSeconds':proposed,'lastLimitingDevice':devices[-1]['type'] if devices else None})
 if not solvers or not rejections:raise ValueError('Missing solver audit')
 return {'windowSeconds':[.001005011,.001005014],'solverCalls':len(solvers),'allAuditedNewtonSolvesConverged':all(x==0 for x in solvers),'rejectedSteps':len(rejections),'firstRejection':rejections[0],'lastRejection':rejections[-1],'adcDecisionChangesInWindow':len(adc)}

def diagnostic(log):
 # "error" in the numeric truncation-estimate record is not an engine error.
 # Strip only complete, syntactically numeric audit records; retain malformed
 # records and interleaved real diagnostics for the ordinary failure checker.
 pattern=r'^(?:TRUNC_AUDIT|TRANSITION_AUDIT) [a-z-]+(?: [a-z0-9]+=[A-Za-z0-9_.+:-]+)+$'
 return solver_diagnostic('\n'.join(l for l in log.splitlines() if not re.fullmatch(pattern,l)))

def assess(root):
 cases={}
 for name in CASES:
  folder=root/name;run=json.loads((folder/'run.json').read_text());log=lzma.open(folder/'ngspice.log.xz','rt').read();failure=diagnostic(log)
  trace=json.loads((folder/'trace-summary.json').read_text()) if (folder/'trace-summary.json').exists() else None
  stop=stop_time((folder/'io.cir').read_text());completed=run['exitCode']==0 and not run.get('timedOut',False) and not failure and trace is not None and abs(trace['lastSeconds']-stop)<1e-12
  cases[name]={'completed':completed,'timedOut':run.get('timedOut',False),'diagnostic':failure,'lastSeconds':trace['lastSeconds'] if trace else None,'requestedStopSeconds':stop,'traceSha256':trace['sha256'] if trace else None}
  if name=='audit':stats=audit_stats(log)
 if cases['control']['traceSha256']!=cases['audit']['traceSha256']:raise ValueError('Logging changed live trajectory')
 if any(cases[n]['completed'] for n in ('control','corners-25','corners-50','corners-12')):raise ValueError('Reassess changed qualification outcome')
 return {'qualified':False,'cases':cases,'auditWaveformByteIdentical':True,'audit':stats,
         'dacCornerRegression':'Compiled original evaluator omits completion breakpoint for an event exactly at the analog boundary. Opt-in candidate schedules the corner without changing single-bit ramp output arithmetic.',
         'candidateAdopted':False,'feedbackPreservedInReduction':True,
         'reductionScope':'Inactive matrix is replaced by fixed low sense inputs. CPU/ROM, bus ADC feedback, supply/filter, serial and LED loads remain live. Failure moves later; this is a reduced failure-class fixture, not an equivalent reproducer of the original event.',
         'interpretation':'The selected live collapse is timestep/error-estimation rejection with converged Newton solves, without an ADC decision change inside the audited window. Recorded-output replay also changes forcing history and breakpoint placement; its completion does not establish a bridge defect. Adding time-grid points alone does not establish convergence.',
         'serviceAcceptance':'Not extended: no completed matched tight pair, and device-model/input-range prerequisites remain unmet.',
         'reviewSha256':sha(Path(__file__))}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--collect',type=Path);p.add_argument('--out',type=Path,required=True);p.add_argument('--verify',action='store_true');a=p.parse_args()
 if a.verify:
  for name,h in json.loads((a.out/'manifest.json').read_text()).items():
   if sha(a.out/name)!=h:raise ValueError('Changed live-transition evidence: '+name)
  if assess(a.out)!=json.loads((a.out/'assessment.json').read_text()):raise ValueError('Stale live-transition assessment')
  print('Live-transition evidence verified; candidate remains unadopted.');return
 if not a.collect:p.error('--collect required')
 a.out.mkdir(parents=True,exist_ok=False)
 for name,relative in CASES.items():
  src=a.collect/relative;out=a.out/name;out.mkdir()
  for f in ('io.cir','run.json'):shutil.copyfile(src/f,out/f)
  with (src/'ngspice.log').open('rb') as inp,lzma.open(out/'ngspice.log.xz','wb') as dest:shutil.copyfileobj(inp,dest)
  if (src/'witness.txt').exists():(out/'trace-summary.json').write_text(json.dumps(extent(src/'witness.txt'),indent=2)+'\n')
 (a.out/'assessment.json').write_text(json.dumps(assess(a.out),indent=2)+'\n')
 (a.out/'manifest.json').write_text(json.dumps({str(f.relative_to(a.out)):sha(f) for f in sorted(a.out.rglob('*')) if f.is_file()},indent=2)+'\n')
if __name__=='__main__':main()
