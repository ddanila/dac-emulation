#!/usr/bin/env python3
"""Review full-window ADC-enabled refinements; rollback qualification is separate."""
import argparse
import json
from pathlib import Path
from audit_log import equal
from compare_firmware_io import sha as logical_sha
from eval_cache_benchmark import verify_dependencies
from ngspice_runtime import verify
from postreset_adc_capture import experiment, SOURCES
from postreset_refinement_review import voltage_gate
from postreset_startup_review import END, FIRMWARE, inspect_log
from raw_pair_review import compare_raw
from ttl7406_probe import sha

HERE = Path(__file__).resolve().parent


def validate_capture(receipt, control, coarse_digest, step):
    if not receipt.get('completed') or receipt.get('error') or receipt.get('exitCode') != 0:
        raise ValueError('Incomplete ADC capture')
    if (receipt['stepNs'],receipt['endSeconds'],receipt['adcCrossings']) != (step,END,'on'):
        raise ValueError('Changed timestep, window or ADC mode')
    expected = dict(control['environment'],ROBOTRON_ADC_CROSSINGS='1')
    if receipt['environment'] != expected: raise ValueError('Changed experimental conditions')
    for key in ('runtime','externalDependencies','candidateBuildSha256','sourceRunSha256'):
        if receipt[key] != control[key]: raise ValueError('Changed '+key)
    if receipt['coarseRunSha256'] != coarse_digest or receipt['originalInputs'] != control['inputs']:
        raise ValueError('Changed baseline provenance')
    if receipt['sources'] != {name:sha(HERE/name) for name in SOURCES}:
        raise ValueError('Changed capture source')
    if set(receipt['inputs']) != set(control['inputs']) or set(receipt['storage']) != {'waveform.raw'}:
        raise ValueError('Changed input or output scope')
    if receipt['log']['exitCode'] != 0: raise ValueError('Failed producer')
    for key,limit in (('bytes','logicalLogBytes'),('compressedBytes','compressedLogBytes')):
        if not 0 < receipt['log'][key] <= receipt['limits'][limit]: raise ValueError('Exceeded log budget')


def assess(coarse, runs):
    if len(runs) != 3: raise ValueError('Need all three prescribed timestep captures')
    control = json.loads((coarse/'run.json').read_text())
    if not control.get('completed') or control.get('error') or control.get('exitCode') != 0 or control['mode'] != 'combined':
        raise ValueError('Need completed combined-fix baseline')
    verify(control['runtime']); verify_dependencies(control['externalDependencies'])
    for name,digest in control['inputs'].items():
        if sha(coarse/name) != digest: raise ValueError('Changed baseline input')
    baseline = inspect_log(coarse/'ngspice.log','combined')
    if logical_sha(coarse/'ngspice.log') != control['logSha256']:
        raise ValueError('Changed baseline log')
    if logical_sha(coarse/'waveform.raw') != control['storage']['waveform.raw']['sha256']:
        raise ValueError('Changed baseline waveform')
    scans = []; receipts = []
    for step,folder in zip((25,12.5,6.25),runs):
        r = json.loads((folder/'run.json').read_text())
        validate_capture(r,control,sha(coarse/'run.json'),step)
        deck,_ = experiment((coarse/'io.cir').read_text(),control['environment'],step,'on')
        if (folder/'io.cir').read_text() != deck: raise ValueError('Changed circuit or stimulus')
        if sha(folder/'build.json') != control['candidateBuildSha256']: raise ValueError('Changed model build')
        for name,digest in r['inputs'].items():
            if sha(folder/name) != digest: raise ValueError('Changed capture input')
            if name != 'io.cir' and digest != control['inputs'][name]: raise ValueError('Changed firmware input')
        for name,digest in (('waveform.raw',r['storage']['waveform.raw']['sha256']),('ngspice.log',r['log']['sha256'])):
            if logical_sha(folder/name) != digest: raise ValueError('Changed retained output')
        scans.append(inspect_log(folder/'ngspice.log','combined')); receipts.append(sha(folder/'run.json'))
    pairs = [compare_raw(runs[i]/'waveform.raw',runs[i+1]/'waveform.raw',
                         [scans[j]['count'] for j in (i,i+1)],END) for i in range(2)]
    effect = compare_raw(coarse/'waveform.raw',runs[0]/'waveform.raw',[baseline['count'],scans[0]['count']],END)
    firmware = [equal(runs[i]/'ngspice.log',runs[i+1]/'ngspice.log',FIRMWARE) for i in range(2)]
    baseline_firmware = equal(coarse/'ngspice.log',runs[0]/'ngspice.log',FIRMWARE)
    gate = voltage_gate(*pairs)
    return {'completed':True,'qualified':False,'numericalGatePassed':gate['passed'] and all(firmware) and baseline_firmware,
            'voltageGate':gate,'comparisons':pairs,'optionEffect':effect,'firmwareRecordsExactlyEqual':firmware,
            'baselineFirmwareRecordsExactlyEqual':baseline_firmware,'stepsNs':[25,12.5,6.25],
            'captureReceipts':receipts,'coarseRunSha256':sha(coarse/'run.json'),'reviewerSha256':sha(Path(__file__)),
            'scope':'Complete 1.16-ms post-reset window, all observed nodes on absolute time; unchanged voltage and non-growth limits.',
            'notEstablished':['ADC-enabled forced-retry/internal-state coverage','Startup and supply recovery','Full-repeat qualification','Device/load admission','Specimen agreement']}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('coarse','enabled','fine','finest','out'):p.add_argument('--'+name,type=Path,required=True)
    a = p.parse_args(); result = assess(a.coarse,[a.enabled,a.fine,a.finest])
    with a.out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
