"""Review a complete ADC decision trace without changing timing acceptance."""
import argparse,json
from pathlib import Path
from adc_decision_review import scan
from delivery_audit_review import scan as delivery_scan
from postreset_adc_decision_capture import SOURCES,experiment
from postreset_startup_review import inspect_log,FIRMWARE
from raw_pair_review import compare_raw
from compare_firmware_io import sha as logical_sha
from audit_log import equal
from retained_evidence import check
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def validate(folder,prior,base):
    r=json.loads((folder/'run.json').read_text())
    if not r['completed'] or r.get('error') or r['exitCode']!=0 or r['log']['exitCode']!=0:raise ValueError('Incomplete capture')
    if (r['mode'],r['stepNs'],r['endSeconds'])!=('on',25,.00116):raise ValueError('Changed full capture scope')
    if r['runtime']!=prior['runtime'] or r['runtimeEnvironment']!=prior['runtimeEnvironment'] or r['externalDependencies']!=prior['externalDependencies']:raise ValueError('Changed selected runtime')
    expected=dict(prior['environment'],ROBOTRON_ADC_TRACE='1')
    if r['environment']!=expected:raise ValueError('Changed ADC experiment')
    if r['sources']!={n:sha(HERE/n) for n in SOURCES}:raise ValueError('Changed capture sources')
    if r['baselineReceiptSha256']!=sha(HERE/'reports/postreset-adc/25/run.json'):raise ValueError('Changed baseline')
    if r['candidateBuildSha256']!=prior['candidateBuildSha256'] or sha(folder/'candidate-build.json')!=r['candidateBuildSha256']:raise ValueError('Changed bridge build')
    bounded=HERE/'reports/adc-decision-board/assessment.json'
    if r['boundedAssessmentSha256']!=sha(bounded) or sha(folder/'bounded-assessment.json')!=sha(bounded):raise ValueError('Changed bounded acceptance')
    if r['inputs']!=prior['inputs'] or any(sha(folder/n)!=h for n,h in r['inputs'].items()):raise ValueError('Changed full input')
    old=[d['path'] for d in base['externalDependencies'] if Path(d['path']).name=='ivlng.vpi'];new=[d['path'] for d in r['externalDependencies'] if Path(d['path']).name=='ivlng.vpi']
    if len(old)!=1 or len(new)!=1:raise ValueError('Ambiguous bridge')
    deck,env=experiment((HERE/'reports/postreset-adc/25/io.cir').read_text(),base['environment'],old[0],new[0],'on',25)
    if (folder/'io.cir').read_text()!=deck or env!=r['environment']:raise ValueError('Changed full experiment')
    if set(r['storage'])!={'waveform.raw'}:raise ValueError('Changed output scope')
    for field,limit in [('bytes','logicalLogBytes'),('compressedBytes','compressedLogBytes')]:
        if not 0<r['log'][field]<=r['limits'][limit]:raise ValueError('Exceeded log budget')
    return r

def assess(folder,prior_folder,prior_assessment):
    bounded=HERE/'reports/adc-decision-board';check(bounded);check(bounded/'adc-source')
    prior=json.loads((prior_folder/'run.json').read_text());base=json.loads((HERE/'reports/postreset-adc/25/run.json').read_text())
    previous=json.loads(prior_assessment.read_text())
    if not prior['completed'] or prior.get('error') or prior['exitCode'] or prior['endSeconds']!=.00116 or prior['mode']!='on' or prior['stepNs']!=25:raise ValueError('Incomplete delivery predecessor')
    comparison=previous['comparison']
    if not previous['firmwareRecordsExactlyEqual'] or not comparison['allSamplesExactlyEqual'] or comparison['endSeconds']!=.00116 or len(comparison['signals'])!=31:raise ValueError('Unqualified delivery predecessor')
    r=validate(folder,prior,base)
    proof=json.loads((bounded/'adc-source/assessment.json').read_text())
    if [m['sha256'] for m in r['runtime']['codeModels'] if Path(m['path']).name=='digital.cm']!=[proof['selectedDigitalSha256']]:raise ValueError('Changed ADC model binding')
    logs={}
    for name,path,receipt in [('prior',prior_folder,prior),('trace',folder,r)]:
        for filename,digest in [('ngspice.log',receipt['log']['sha256']),('waveform.raw',receipt['storage']['waveform.raw']['sha256'])]:
            if logical_sha(path/filename)!=digest:raise ValueError('Changed full output')
        logs[name]=inspect_log(path/'ngspice.log','combined')
    result=compare_raw(prior_folder/'waveform.raw',folder/'waveform.raw',[logs[n]['count'] for n in ('prior','trace')],.00116,exact=True)
    if not equal(prior_folder/'ngspice.log',folder/'ngspice.log',FIRMWARE):raise ValueError('ADC tracing changed firmware')
    if not equal(prior_folder/'ngspice.log',folder/'ngspice.log',('DELIVERY_AUDIT ',)):raise ValueError('ADC tracing changed exact delivery records')
    delivery=delivery_scan(folder/'ngspice.log')
    if delivery!=previous['audit']:raise ValueError('ADC tracing changed delivery records')
    return dict(qualified=False,controlsPassed=True,comparison=result,firmwareRecordsExactlyEqual=True,delivery=delivery,adcDecisions=scan(folder),logs=logs,receiptSha256=sha(folder/'run.json'),priorReceiptSha256=sha(prior_folder/'run.json'),priorAssessmentSha256=sha(prior_assessment),scope='Complete 1.16-ms logging-only ADC decision control. Exact waveform, firmware and delivery comparison; all observed scalar inputs bind to sampled ADC decisions. No clamp correction, exact crossing claim, complete rejected-step history, convergence qualification or full-repeat execution.')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('root','prior','prior-assessment','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.out.write_text(json.dumps(assess(a.root,a.prior,a.prior_assessment),indent=2)+'\n')
