#!/usr/bin/env python3
"""Capture the full post-reset delivery audit after exact bounded controls."""
import argparse
import json
import math
from pathlib import Path
import shutil
import time
from bounded_log_process import run as producer
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from ngspice_runtime import verify
from postreset_refinement_capture import refined_deck
from postreset_startup_review import inspect_log
from stop_board_capture import runtime_environment
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
SOURCES=('postreset_delivery_capture.py','delivery_audit_review.py','output_drain_board_review.py','raw_pair_review.py','postreset_refinement_capture.py','postreset_startup_review.py',
         'bounded_log_process.py','compressed_output.py','stop_board_capture.py')


def experiment(deck, environment, old_vpi, new_vpi, mode, step):
    if mode not in ('off','tick','on','retry') or step not in (25,12.5,6.25) or (mode!='on' and step!=25):
        raise ValueError('Unsupported mode/step')
    if old_vpi==new_vpi or deck.count(old_vpi)!=1:raise ValueError('Need unique candidate VPI substitution')
    if environment.get('ROBOTRON_ADC_CROSSINGS')!='1' or any(k.startswith('ROBOTRON_FORCE_') or k in ('ROBOTRON_ABSOLUTE_TICKS','ROBOTRON_DRAIN_TICK','ROBOTRON_NEWTON_REJECT_START') for k in environment):
        raise ValueError('Need unmodified ADC-enabled baseline')
    refined_deck(deck,12.5)  # Validate the original complete window/reset contract.
    result=deck if step==25 else refined_deck(deck,step)
    env=dict(environment)
    if mode!='off':env['ROBOTRON_ABSOLUTE_TICKS']='1'
    if mode in ('on','retry'):env['ROBOTRON_DRAIN_TICK']='1'
    if mode=='retry':env.update(ROBOTRON_FORCE_NEWTON_REJECT='1',ROBOTRON_NEWTON_REJECT_START='0.0011')
    return result.replace(old_vpi,new_vpi),env


def run(a):
    if not math.isfinite(a.timeout) or a.timeout<=0:raise ValueError('Need positive timeout')
    source=a.source.resolve();candidate=a.candidate.resolve();out=a.out.resolve()
    base=json.loads((source/'run.json').read_text());known=HERE/'reports/postreset-adc/25/run.json'
    if sha(source/'run.json')!=sha(known) or not base['completed']:raise ValueError('Changed reviewed ADC baseline')
    from delivery_audit_review import assess
    reviewed=assess(a.bounded_root)
    if reviewed!=json.loads(a.bounded_assessment.read_text()):
        raise ValueError('Changed complete delivery audit qualification')
    bounded=reviewed['boardAssessment']
    if not bounded.get('completed') or not bounded.get('disabledControlPassed') or not all(bounded['firmwareRecordsExactlyEqual'].values()):
        raise ValueError('Need completed bounded disabled/retry controls')
    for mode in ('off','tick','on','retry'):
        r=json.loads((a.bounded_root/mode/'run.json').read_text())
        if sha(a.bounded_root/mode/'run.json')!=bounded['receipts'][mode] or r['candidateBuildSha256']!=sha(candidate/'build.json'):
            raise ValueError('Changed bounded candidate provenance')
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed candidate')
    old=[d['path'] for d in base['externalDependencies'] if Path(d['path']).name=='ivlng.vpi']
    if len(old)!=1:raise ValueError('Ambiguous original VPI')
    for n,h in base['inputs'].items():
        if sha(source/n)!=h:raise ValueError('Changed original input')
    env=runtime_environment(base);verify_dependencies(base['externalDependencies'])
    deck,options=experiment((source/'io.cir').read_text(),base['environment'],old[0],str(candidate/'ivlng.vpi'),a.mode,a.step_ns)
    env.update(options)
    required=3*base['storage']['waveform.raw']['bytes']+1024**3
    if shutil.disk_usage(out.parent).free<required:raise ValueError('Insufficient capture capacity')
    out.mkdir(exist_ok=False);(out/'io.cir').write_text(deck)
    for n in base['inputs']:
        if n!='io.cir':shutil.copy2(source/n,out/n)
    shutil.copy2(candidate/'build.json',out/'candidate-build.json')
    shutil.copy2(a.bounded_assessment,out/'bounded-assessment.json')
    deps=external_dependencies(out,{'deck':'io.cir','inputs':['io.vvp','s600.hex']})
    limits={'timeoutSeconds':a.timeout,'logicalLogBytes':4*1024**3,'compressedLogBytes':512*1024**2,'freeSpaceReserveBytes':512*1024**2}
    r={'completed':False,'qualified':False,'mode':a.mode,'stepNs':a.step_ns,'endSeconds':.00116,
       'runtime':base['runtime'],'runtimeEnvironment':{'SPICE_SCRIPTS':env['SPICE_SCRIPTS']},'environment':options,
       'externalDependencies':deps,'inputs':{n:sha(out/n) for n in base['inputs']},
       'baselineReceiptSha256':sha(source/'run.json'),'candidateBuildSha256':sha(out/'candidate-build.json'),
       'boundedAssessmentSha256':sha(out/'bounded-assessment.json'),'sources':{n:sha(HERE/n) for n in SOURCES},
       'limits':limits,'requiredFreeBytes':required,'scope':'Complete 1.16-ms ADC-enabled post-reset window. Only candidate VPI, its opt-in mode, timestep and explicit forced rejection may change. Not full repeat or closed-board startup.'}
    start=time.monotonic();(out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    try:
        with capture(out,['waveform.raw']) as storage:
            log=producer([base['runtime']['executable']['path'],'-n','-b','io.cir'],out,env,out/'ngspice.log.xz',a.timeout,
                         logical_limit=limits['logicalLogBytes'],compressed_limit=limits['compressedLogBytes'],min_free_bytes=limits['freeSpaceReserveBytes'])
        r.update(storage=storage,log=log,exitCode=log['exitCode'])
        verify(base['runtime']);verify_dependencies(deps)
        if any(sha(out/n)!=h for n,h in r['inputs'].items()):raise ValueError('Changed capture input')
        if sha(candidate/'build.json')!=r['candidateBuildSha256']:raise ValueError('Changed candidate build')
        if log['exitCode']!=0:raise ValueError('Producer failed')
        r['logSummary']=inspect_log(out/'ngspice.log','retry' if a.mode=='retry' else 'combined')
        r['completed']=True
    except Exception as exc:
        r['error']=str(exc);raise
    finally:
        r['elapsedSeconds']=time.monotonic()-start;(out/'run.json').write_text(json.dumps(r,indent=2)+'\n')
    print(out/'run.json',flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','candidate','bounded-root','bounded-assessment','out'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--mode',choices=('off','tick','on','retry'),required=True)
    p.add_argument('--step-ns',choices=(25,12.5,6.25),type=float,required=True)
    p.add_argument('--timeout',type=float,default=28800)
    run(p.parse_args())
