#!/usr/bin/env python3
"""Queue full ADC logging after the unchanged full delivery control passes."""
import argparse,json,os,subprocess,time,traceback
from pathlib import Path
from types import SimpleNamespace
import postreset_adc_decision_capture as capture
from postreset_adc_decision_review import assess
from cached_net_board_review import sources
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def run(local,candidate):
    local=local.resolve();candidate=candidate.resolve()
    predecessor=local/'postreset-delivery-job.json';prior=json.loads(predecessor.read_text());pid=prior['pid']
    pins=sources()
    for name in capture.SOURCES:pins[name]=sha(HERE/name)
    pins['test_postreset_adc_decision.py']=sha(HERE/'test_postreset_adc_decision.py')
    status=local/'postreset-adc-decision-job.json'
    if status.exists():raise ValueError('Existing ADC job must be preserved')
    process=subprocess.run(['ps','-p',str(pid),'-o','lstart=,command='],text=True,capture_output=True)
    identity=process.stdout.strip() if process.returncode==0 else None
    if identity is None:
        if prior['state']!='passed':raise ValueError('Missing delivery predecessor before acceptance')
    elif 'postreset-delivery-job.py' not in identity:raise ValueError('Wrong delivery predecessor')
    root=local/'postreset-adc-decision-on-25'
    def save(state,**kw):status.write_text(json.dumps(dict(state=state,pid=os.getpid(),predecessorPid=pid,predecessorIdentity=identity,sources=pins,**kw),indent=2)+'\n')
    def verify():
        for name,digest in dict(prior['sources'],**pins).items():
            if sha(HERE/name)!=digest:raise ValueError('Changed pinned source: '+name)
    try:
        verify();save('waiting-delivery-review')
        while identity is not None:
            p=subprocess.run(['ps','-p',str(pid),'-o','lstart=,command='],text=True,capture_output=True)
            if p.returncode:break
            if p.stdout.strip()!=identity:raise ValueError('Delivery predecessor PID reused')
            verify();time.sleep(10)
        verify();final=json.loads(predecessor.read_text())
        if final['state']!='passed' or final['pid']!=pid or final['sources']!=prior['sources']:raise ValueError('Full delivery control did not pass')
        previous=local/'postreset-delivery-assessment.json';previous_sha=sha(previous)
        save('capturing',priorAssessmentSha256=previous_sha)
        bounded=HERE/'reports/adc-decision-board'
        capture.run(SimpleNamespace(source=HERE/'reports/postreset-adc/25',candidate=candidate,bounded_root=bounded,bounded_assessment=bounded/'assessment.json',out=root,mode='on',step_ns=25,timeout=28800))
        verify();save('reviewing',priorAssessmentSha256=previous_sha)
        if sha(previous)!=previous_sha:raise ValueError('Changed predecessor assessment')
        result=assess(root,local/'postreset-delivery-on-25',previous)
        verify()
        if sha(previous)!=previous_sha:raise ValueError('Changed predecessor assessment during review')
        output=local/'postreset-adc-decision-assessment.json'
        with output.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
        save('passed',assessmentSha256=sha(output),priorAssessmentSha256=previous_sha)
    except Exception as exc:
        save('failed',error=str(exc),traceback=traceback.format_exc());raise

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--local',type=Path,required=True);p.add_argument('--candidate',type=Path,required=True)
    a=p.parse_args();run(a.local,a.candidate)
