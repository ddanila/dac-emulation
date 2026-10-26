#!/usr/bin/env python3
"""Review matched 20-us ADC controls without claiming post-reset execution."""
import argparse
import json
from pathlib import Path
from audit_log import scan, records
from compare_firmware_io import sha as logical_sha
from eval_cache_benchmark import verify_dependencies
from ngspice_runtime import verify
from postreset_refinement_capture import ORIGINAL_TRAN
from postreset_refinement_review import voltage_gate
from raw_pair_review import compare_raw
from ttl7406_probe import sha


def assess(root, coarse, producer):
    control = json.loads((coarse/'run.json').read_text())
    if not control.get('completed') or control.get('error') or control.get('exitCode') != 0:
        raise ValueError('Incomplete combined-fix baseline')
    original = (coarse/'io.cir').read_text()
    if original.count(ORIGINAL_TRAN) != 1:
        raise ValueError('Changed full-window baseline')
    for name, digest in control['inputs'].items():
        if sha(coarse/name) != digest: raise ValueError('Changed baseline input')
    verify(control['runtime']); verify_dependencies(control['externalDependencies'])
    scans = {}; receipts = {}; coverage = {}
    for mode in ('off', 'on'):
        for step in (25, 12.5, 6.25):
            name = f'{mode}-{step:g}'; folder = root/name
            r = json.loads((folder/'run.json').read_text())
            if r.get('error') not in (None, 'Missing bus observations'):
                raise ValueError('Failed capture: '+name)
            # The original producer reused a post-reset bus check on a pre-reset
            # window. Revalidate transport, diagnostics and every raw sample here;
            # never convert its flag into a full-window acceptance claim.
            if r['log']['exitCode'] != 0: raise ValueError('Failed simulator')
            if (r['stepNs'], r['endSeconds'], r['adcCrossings']) != (step, 20e-6, mode):
                raise ValueError('Changed experiment scope')
            expected_env = dict(control['environment'])
            if mode == 'on': expected_env['ROBOTRON_ADC_CROSSINGS'] = '1'
            if r['environment'] != expected_env: raise ValueError('Changed environment')
            for key in ('runtime', 'externalDependencies', 'candidateBuildSha256'):
                if r[key] != control[key]: raise ValueError('Changed '+key)
            if r['coarseRunSha256'] != sha(coarse/'run.json') or r['producerSha256'] != sha(producer):
                raise ValueError('Changed provenance')
            if (folder/'io.cir').read_text() != original.replace(ORIGINAL_TRAN, f'\n.tran {step:g}n 20000n\n'):
                raise ValueError('Changed circuit or stimulus')
            if set(r['inputs']) != set(control['inputs']): raise ValueError('Changed input scope')
            for file, digest in r['inputs'].items():
                if sha(folder/file) != digest: raise ValueError('Changed capture input')
                if file != 'io.cir' and digest != control['inputs'][file]: raise ValueError('Changed HDL/ROM')
            for file, digest in (('ngspice.log',r['log']['sha256']), ('waveform.raw',r['storage']['waveform.raw']['sha256'])):
                if logical_sha(folder/file) != digest: raise ValueError('Changed retained output')
            s = scan(folder/'ngspice.log')
            if s['diagnostic'] or s['sorry'] or not s['count'] or s['faults'] or not s['latchesMatch']:
                raise ValueError('Invalid bounded diagnostic control')
            if list(records(folder/'ngspice.log', ('HISTORY_INIT ',))) != ['HISTORY_INIT seed=none initialized=1 ports=69']:
                raise ValueError('Missing combined-fix initialization')
            if any(s['busCounts']): raise ValueError('Unexpected pre-reset bus traffic')
            coverage[name] = compare_raw(folder/'waveform.raw',folder/'waveform.raw',[s['count']]*2,20e-6,exact=True)
            scans[name] = s; receipts[name] = sha(folder/'run.json')
    comparisons = {}
    for mode in ('off','on'):
        names = [f'{mode}-{step:g}' for step in (25,12.5,6.25)]
        pairs = [compare_raw(root/names[i]/'waveform.raw',root/names[i+1]/'waveform.raw',
                            [scans[names[j]]['count'] for j in (i,i+1)],20e-6) for i in range(2)]
        comparisons[mode] = {'pairs':pairs,'voltageGate':voltage_gate(*pairs)}
    effects = {str(step):compare_raw(root/f'off-{step:g}'/'waveform.raw',root/f'on-{step:g}'/'waveform.raw',
                                    [scans[f'{mode}-{step:g}']['count'] for mode in ('off','on')],20e-6)
               for step in (25,12.5,6.25)}
    return {'completed':True,'qualified':False,'scope':'Whole 20-us pre-reset screen; no post-reset firmware, startup-inclusive board qualification or full-window convergence claim.',
            'coverage':coverage,'receipts':receipts,'comparisons':comparisons,'optionEffect':effects,
            'reviewerSha256':sha(Path(__file__))}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('root','coarse','producer','out'): p.add_argument('--'+name,type=Path,required=True)
    a = p.parse_args(); result = assess(a.root,a.coarse,a.producer)
    with a.out.open('x') as f: json.dump(result,f,indent=2); f.write('\n')
