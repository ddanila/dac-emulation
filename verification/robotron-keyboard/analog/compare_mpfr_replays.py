#!/usr/bin/env python3
"""Compare completed analog-only MPFR replay voltages without phase alignment."""
import argparse
import json
from pathlib import Path
import re

from analog_driver_replay import sha
from failure_evidence import solver_diagnostic
from host_waveform_comparison import rows, compare_samples

HERE=Path(__file__).resolve().parent
AUDIT_PREFIXES=('TRUNC_AUDIT ','TRANSITION_AUDIT ','NODE_AUDIT ','INDUCTOR_AUDIT ','LINEAR_AUDIT ')


def step_and_normalized(deck):
    matches=list(re.finditer(r'^\.tran ([0-9]+(?:\.[0-9]+)?)n ([0-9.eE+-]+)$',deck,re.M))
    if len(matches)!=1:raise ValueError('Expected one simple transient command')
    match=matches[0]
    return float(match[1]),deck[:match.start(1)]+'STEP'+deck[match.end(1):]


def compatible(first,second,kind):
    a,b=first['report'],second['report']
    for field in ('sourceReportSha256','ngspiceRuntime','patchSha256','stopSeconds','integration'):
        if a[field]!=b[field]:raise ValueError('Mismatched '+field)
    if first['normalizedDeck']!=second['normalizedDeck']:
        raise ValueError('Circuit, stimulus or controls differ beyond transient step')
    if a['artifacts']['build-provenance.json']!=b['artifacts']['build-provenance.json']:
        raise ValueError('Build provenance differs')
    if kind=='precision':
        if a['mode']!='256' or b['mode']!='512' or first['stepNs']!=second['stepNs']:
            raise ValueError('Expected only 256-to-512 precision change')
    elif kind=='timestep':
        if a['mode']!=b['mode'] or first['stepNs']!=2*second['stepNs']:
            raise ValueError('Expected only halved timestep at the same precision')
    else:raise ValueError('Unknown comparison')


def load(directory):
    report=json.loads((directory/'report.json').read_text())
    if (report.get('error') or report['mode'] not in ('256','512') or
        report['exitCode']!=0 or report['precisionGuardDiagnostics'] or
        report['integration']['selection']!='gear' or not report.get('effectiveIntegrationVerified')):
        raise ValueError('Expected completed experimental Gear/MPFR replay')
    for name,digest in report['artifacts'].items():
        if sha(directory/name)!=digest:raise ValueError('Changed capture '+name)
    # Preserve the original report, including the known options-heading false positive.
    log=(directory/'ngspice.log').read_text()
    messages='\n'.join(line for line in log.splitlines() if not line.startswith(AUDIT_PREFIXES))
    if solver_diagnostic(messages):raise ValueError('Solver diagnostic remains')
    if not report['completed'] and report['solverDiagnostic']!='Truncation error correction, charge based, is selected:':
        raise ValueError('Unexplained producer failure')
    if len(report['waveforms'])!=4 or any(v['rows']<=0 or abs(v['lastSampleSeconds']-report['stopSeconds'])>1e-15
                                       for v in report['waveforms'].values()):
        raise ValueError('Incomplete producer waveforms')
    step,deck=step_and_normalized((directory/'io.cir').read_text())
    with (directory/'host-trace.txt').open() as stream:header=stream.readline().split()
    if len(header)!=7 or header[0]!='time' or any(not name.lower().startswith('v(') for name in header[1:]):
        raise ValueError('Expected six host voltage signals')
    return {'report':report,'normalizedDeck':deck,'stepNs':step,'signals':header[1:]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('coarse',type=Path)
    parser.add_argument('fine',type=Path)
    parser.add_argument('--kind',choices=('precision','timestep'),required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    captures=[load(p) for p in (args.coarse,args.fine)]
    compatible(*captures,args.kind)
    if captures[0]['signals']!=captures[1]['signals']:raise ValueError('Different voltage observations')
    observation=compare_samples(*(rows(p/'host-trace.txt',c['signals'],c['stepNs'])
                                  for p,c in zip((args.coarse,args.fine),captures)))
    for name,entry in zip(captures[0]['signals'],observation['signals']):entry['signal']=name
    result={'completed':True,'qualified':False,'scope':__doc__,'kind':args.kind,
        'sources':{n:sha(HERE/n) for n in ('compare_mpfr_replays.py','host_waveform_comparison.py','failure_evidence.py','trace_io.py','analog_driver_replay.py','compare_firmware_io.py',
                                                       'transient_analysis.py','serial_observation.py','led_observation.py')},
        'reports':{label:sha(p/'report.json') for label,p in [('coarse',args.coarse),('fine',args.fine)]},
        'stepsNs':[c['stepNs'] for c in captures], 'observation':observation,
        'boundary':'Whole saved interval at absolute time, using piecewise-linear interpolation on the union of original knots. No phase alignment or physical accuracy budget. Timestep refinement also changes ngspice-derived delmin. Completion and small duration-weighted errors cannot waive peak differences or device qualification.'}
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    print(args.out)


if __name__=='__main__':main()
