#!/usr/bin/env python3
"""Paired complete live controls for direct raw output; no circuit changes."""
import argparse
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
from compressed_output import capture
from eval_cache_benchmark import external_dependencies, verify_dependencies
from filter_truncation_log import diagnostic
from ngspice_runtime import identify, verify
from ttl7406_probe import sha


def raw_deck(deck):
    commands = re.findall(r'^wrdata\s+(\S+)\s+(.+)$', deck, re.M)
    if not commands or len(re.findall(r'^run$', deck, re.M)) != 1:
        raise ValueError('Expected one run and explicit waveform writers')
    if re.search(r'^\s*(?:set\s+filetype|stop|resume|write|linearize|let)\b', deck, re.M | re.I):
        raise ValueError('Unsupported control command in raw output comparison')
    result = re.sub(r'^wrdata\s+.+\n', '', deck, flags=re.M)
    return result.replace('\nrun\n', '\nset filetype=binary\nrun waveform.raw\n'), commands


def run_pair(baseline, runtime_path, spinit, out, timeout, *, rollback_audit=False):
    baseline = baseline.resolve()
    receipt = json.loads((baseline/'run.json').read_text())
    if receipt['exitCode'] != 0 or receipt['timedOut'] or receipt['solverDiagnostic'] or receipt['haltNs'] is not None:
        raise ValueError('Need a complete unhalted baseline')
    if not (receipt['dacAnchored'] and receipt['conservativeCap'] and receipt['passiveAssembly']
            and receipt['mpfrTransitionBits'] == '256' and receipt['mpfrStartNs'] == 0
            and receipt['enabled'] and receipt.get('observationSignals')):
        raise ValueError('Unsupported baseline runtime configuration')
    for key in ('adcCrossings','audit','stateAudit','switchAudit','capPairedRhs','inductorMonitor',
                'matrixBoundarySubstitution','filterTruncAudit','startupTruncAudit','dacStateAudit'):
        if receipt.get(key):
            raise ValueError('Unsupported baseline mode: '+key)
    deck = (baseline/'io.cir').read_text()
    if sha(baseline/'io.cir') != receipt['deckSha256']:
        raise ValueError('Changed baseline deck')
    if receipt.get('rawOutput'):
        if not rollback_audit:
            raise ValueError('Raw baseline requires rollback audit controls')
        if len(re.findall(r'^run waveform\.raw$', deck, re.M)) != 1 or re.search(r'^wrdata\b', deck, re.M):
            raise ValueError('Expected one direct raw writer')
        transformed, writers = deck, []
    else:
        transformed, writers = raw_deck(deck)
    saves = re.findall(r'^\.save (.+)$', deck, re.M)
    if len(saves) != 1 or set(saves[0].split()) != set(receipt['observationSignals']):
        raise ValueError('Baseline does not observe every saved signal')
    runtime, env = identify(runtime_path, spinit)
    if runtime['spinit'] != receipt['runtime']['spinit'] or runtime['codeModels'] != receipt['runtime']['codeModels']:
        raise ValueError('Changed code-model dependencies')
    deps = external_dependencies(baseline, {'deck':'io.cir','inputs':['io.vvp','s600.hex']})
    if deps != receipt['externalDependencies']:
        raise ValueError('Changed live dependencies')
    for key in list(env):
        if key.startswith('ROBOTRON_'):
            del env[key]
    env.update(ROBOTRON_EVAL_CACHE='off', ROBOTRON_DAC_ANCHORED='1',
               ROBOTRON_DAC_BREAKPOINTS='1', ROBOTRON_MPFR_BITS='256',
               ROBOTRON_MPFR_TRANSITION_ONLY='1', ROBOTRON_MPFR_START='0',
               ROBOTRON_CAP_ASSEMBLY='exact', ROBOTRON_POSTCAP_ASSEMBLY='exact')
    out.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(__file__, out/'capture-generator.py')
    (out/'baseline.json').write_text(json.dumps(receipt,indent=2)+'\n')
    controls = ([('off', transformed, ['waveform.raw']), ('on', transformed, ['waveform.raw'])]
                if rollback_audit else [('memory', deck, [name for name,_ in writers]),
                                       ('pipe', transformed, ['waveform.raw'])])
    for label, text, names in controls:
        env.pop('ROBOTRON_ROLLBACK_AUDIT', None)
        if rollback_audit and label == 'on':
            env['ROBOTRON_ROLLBACK_AUDIT'] = '1'
        directory = out/label
        directory.mkdir()
        for name in ('io.vvp','s600.hex'):
            if sha(baseline/name) != receipt['inputs'][name]:
                raise ValueError('Changed baseline input')
            shutil.copyfile(baseline/name,directory/name)
        (directory/'io.cir').write_text(text)
        start = time.monotonic()
        result = {'runtime': runtime, 'externalDependencies': deps,
                  'inputs': receipt['inputs'], 'deckSha256':sha(directory/'io.cir'),
                  'baselineRunSha256':sha(baseline/'run.json'), 'mode':label,
                  'environment':{k:v for k,v in env.items() if k.startswith('ROBOTRON_')},
                  'qualified':False, 'exitCode':None, 'timedOut':False}
        try:
            with capture(directory,names) as storage:
                with (directory/'ngspice.log').open('w') as log:
                    process = subprocess.run([str(runtime_path),'-n','-b','io.cir'],cwd=directory,
                                             env=env,stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
                result['exitCode'] = process.returncode
                if process.returncode:
                    raise ValueError('Live producer failed')
            result['storage'] = storage
            verify(runtime)
            verify_dependencies(deps)
            result['solverDiagnostic'] = diagnostic((directory/'ngspice.log').read_text())
            if result['solverDiagnostic']:
                raise ValueError('Live solver diagnostic')
        except Exception as exc:
            result['error'] = str(exc)
            result['timedOut'] = isinstance(exc, subprocess.TimeoutExpired)
            raise
        finally:
            result['elapsedSeconds'] = time.monotonic()-start
            (directory/'run.json').write_text(json.dumps(result,indent=2)+'\n')
            print(directory/'run.json',flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('baseline','runtime','spinit','out'):
        p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--timeout',type=float,default=3600)
    p.add_argument('--rollback-audit',action='store_true',help='Compare complete raw captures with rollback logging off/on')
    a=p.parse_args()
    run_pair(a.baseline,a.runtime.resolve(),a.spinit,a.out,a.timeout,rollback_audit=a.rollback_audit)
