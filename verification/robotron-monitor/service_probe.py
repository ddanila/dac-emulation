"""Run one independently loaded SPICE trace per K7222 service point.

Only a circuit re-solve can represent the probe's effect on a nonlinear node.
The unprobed deck and trace are retained for the raw comparison.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
REGISTER=ROOT/'reference/k7222-11/service-observations.json'
INSTRUMENT=ROOT/'reference/k7222-11/service-instrument.json'


def digest(path):
    result=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda:stream.read(1024*1024),b''):
            result.update(block)
    return result.hexdigest()


def instrument_values():
    data=json.loads(INSTRUMENT.read_text())
    if data.get('format')!='dac-monitor-service-instrument-v1':
        raise ValueError('unsupported service instrument')
    resistance=data['direct_input_resistance_ohm']['value']
    capacitance=data['direct_input_capacitance_f']['value']
    if not all(type(value) in (int,float) and math.isfinite(value) and value>0
               for value in (resistance,capacitance)):
        raise ValueError('invalid service probe impedance')
    return resistance,capacitance


def loaded_deck(base, node, resistance, capacitance):
    """Add one direct EO 203 equivalent at a top-level node before .end."""
    if not re.fullmatch(r'[a-zA-Z][a-zA-Z0-9_]*',node):
        raise ValueError('probe requires a top-level circuit node')
    lines=base.splitlines(keepends=True)
    if not lines or lines[-1].strip().lower()!='.end':
        raise ValueError('circuit deck must end in .end')
    if any(line.strip().lower()=='.end' for line in lines[:-1]):
        raise ValueError('circuit deck has multiple .end directives')
    if not all(math.isfinite(value) and value>0 for value in (resistance,capacitance)):
        raise ValueError('invalid probe impedance')
    return (''.join(lines[:-1])
            +f'Rserviceprobe {node} 0 {resistance:.17g}\n'
            +f'Cserviceprobe {node} 0 {capacitance:.17g}\n'
            +lines[-1])


def run(base_deck, base_trace, output, points, *, solver='ngspice', timeout_s=3600):
    base_deck=Path(base_deck).resolve();base_trace=Path(base_trace).resolve()
    output=Path(output).resolve()
    if output.exists():raise FileExistsError(output)
    if not base_deck.is_file() or not base_trace.is_file():
        raise ValueError('unprobed deck and trace are required')
    binary=shutil.which(str(solver))
    if binary is None:raise FileNotFoundError('ngspice solver not found')
    if not math.isfinite(timeout_s) or timeout_s<=0:raise ValueError('invalid timeout')
    register=json.loads(REGISTER.read_text())
    by_point={item['test_point']:item for item in register['waveforms']}
    points=sorted(set(points))
    if not points or set(points)-set(by_point):raise ValueError('unknown or empty point selection')
    resistance,capacitance=instrument_values()
    base=base_deck.read_text();output.mkdir(parents=True)
    manifest=dict(format='dac-monitor-service-probe-traces-v1',
                  base_deck=str(base_deck),base_deck_sha256=digest(base_deck),
                  input=str(base_trace),input_sha256=digest(base_trace),
                  register_sha256=digest(REGISTER),instrument_sha256=digest(INSTRUMENT),
                  solver=str(Path(binary).resolve()),requested_points=points,cases=[])
    for number in points:
        item=by_point[number];node=item['model_node']
        case=output/str(number);case.mkdir()
        (case/'run.cir').write_text(loaded_deck(base,node,resistance,capacitance))
        with (case/'process.log').open('w') as log:
            result=subprocess.run([binary,'-n','-b','-r','trace.raw','-o','solver.log','run.cir'],
                                  cwd=case,stdout=log,stderr=subprocess.STDOUT,timeout=timeout_s)
        solver_log=(case/'solver.log').read_text() if (case/'solver.log').exists() else ''
        if result.returncode or re.search(r'(?i)timestep too small|aborted|fatal|error',solver_log):
            raise RuntimeError(f'probe solve failed at point {number}: {case}')
        trace=case/'trace.raw'
        if not trace.is_file():raise RuntimeError(f'probe trace missing at point {number}')
        # The scorer validates both the trace content and the exact generated deck.
        manifest['cases'].append(dict(test_point=number,model_node=node,
            model_expression=item['model_expression'].lower(),
            resistance_ohm=resistance,capacitance_f=capacitance,
            deck=str(case/'run.cir'),deck_sha256=digest(case/'run.cir'),
            trace=str(trace),trace_sha256=digest(trace),
            solver_log_sha256=digest(case/'solver.log')))
    manifest['status']='complete'
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return output/'manifest.json'


def validate(manifest_path, input_path):
    manifest_path=Path(manifest_path)
    manifest=json.loads(manifest_path.read_text())
    if manifest.get('format')!='dac-monitor-service-probe-traces-v1':
        raise ValueError('unsupported probe trace manifest')
    if manifest.get('status')!='complete':raise ValueError('incomplete probe solve manifest')
    base=Path(manifest['base_deck']);input_path=Path(input_path)
    if (Path(manifest['input']).resolve()!=input_path.resolve()
            or manifest['input_sha256']!=digest(input_path)
            or manifest['base_deck_sha256']!=digest(base)
            or manifest['register_sha256']!=digest(REGISTER)
            or manifest['instrument_sha256']!=digest(INSTRUMENT)):
        raise ValueError('probe manifest differs from current input or model')
    register=json.loads(REGISTER.read_text())
    by_point={item['test_point']:item for item in register['waveforms']}
    resistance,capacitance=instrument_values()
    expected={}
    for case in manifest['cases']:
        number=case['test_point']
        if number in expected or number not in by_point:raise ValueError('duplicate or unknown probe point')
        item=by_point[number];node=item['model_node']
        deck=Path(case['deck']);trace=Path(case['trace'])
        generated=loaded_deck(base.read_text(),node,resistance,capacitance)
        if (case['model_node']!=node or case['model_expression']!=item['model_expression'].lower()
                or case['resistance_ohm']!=resistance or case['capacitance_f']!=capacitance
                or deck.read_text()!=generated or case['deck_sha256']!=digest(deck)
                or case['trace_sha256']!=digest(trace)
                or case['solver_log_sha256']!=digest(deck.parent/'solver.log')):
            raise ValueError(f'probe trace or circuit differs at point {number}')
        expected[number]=trace
    if sorted(expected)!=manifest['requested_points']:
        raise ValueError('probe manifest does not cover the requested points')
    return expected


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base_deck',type=Path)
    parser.add_argument('base_trace',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--points',required=True,help='comma-separated service point numbers')
    parser.add_argument('--solver',default='ngspice')
    parser.add_argument('--timeout-s',type=float,default=3600)
    args=parser.parse_args()
    points=[int(item) for item in args.points.split(',')]
    print(run(args.base_deck,args.base_trace,args.output,points,
              solver=args.solver,timeout_s=args.timeout_s))


if __name__=='__main__':main()
