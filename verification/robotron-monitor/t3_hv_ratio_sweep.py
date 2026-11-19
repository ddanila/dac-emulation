"""Compare the current T3 turns hypothesis with the conditional A5 EHT ratio."""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import subprocess
import tempfile

import transformer_candidates

ROOT=Path(__file__).resolve().parent
GRAPH=ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
PARAMETERS=ROOT/'reference/k7222-11/t3-initial-parameters.json'
DESIGN=ROOT/'reference/k7222-11/design-point.json'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def pulse(graph,parameters,turns,window):
    candidate=next(item for item in transformer_candidates.enumerate_candidates(graph)
                   if item['polarity']['high_voltage']==-1)
    modified=copy.deepcopy(parameters)
    modified['groups']['high_voltage'][0]['turns']['value']=turns
    model,metadata=transformer_candidates.compile_model(graph,candidate,modified)
    ports=metadata['ports']
    nodes=['0' if port=='X2_4' else port for port in ports]
    shunts=[f'Rref{index} {port} 0 1G' for index,port in enumerate(ports)
            if port not in ('X2_7','X2_4')]
    with tempfile.TemporaryDirectory() as directory:
        out=Path(directory);deck=out/'pulse.cir';trace=out/'trace.txt'
        deck.write_text('\n'.join([
            'T3 isolated open-circuit HV ratio diagnostic',model,
            'Vdrive X2_7 0 PULSE(0 1 20n 1n 1n 16u 40u)',*shunts,
            'Xtest '+' '.join(nodes)+' T3_CANDIDATE',
            '.control','tran 20n 16u',f'wrdata {trace} v(X1_1,X1_16) v(X2_7)',
            'quit','.endc','.end',
        ])+'\n')
        result=subprocess.run(['ngspice','-b',str(deck)],capture_output=True,text=True,check=True)
        if 'Error:' in result.stdout+result.stderr:raise ValueError('ngspice error')
        rows=[list(map(float,line.split())) for line in trace.read_text().splitlines()
              if line.strip()]
    if not rows or any(len(row)!=4 for row in rows):
        raise ValueError('incomplete T3 ratio trace')
    selected=[row for row in rows if window[0]<=row[0]<=window[1]]
    if len(selected)<100 or any(abs(row[3]-1)>1e-6 for row in selected):
        raise ValueError('T3 drive/window absent')
    values=[row[1] for row in selected]
    return dict(turns=turns,ideal_open_circuit_ratio=turns/sum(
                    section['turns']['value'] for section in parameters['groups']['drive']),
                isolated_window_mean_ratio=statistics.mean(values),
                isolated_window_min_ratio=min(values),
                isolated_window_max_ratio=max(values),
                representative_polarity=candidate['polarity'])


def run():
    graph=json.loads(GRAPH.read_text());parameters=json.loads(PARAMETERS.read_text())
    design=json.loads(DESIGN.read_text())
    ratio=design['high_voltage_ratio']['ratio_if_boost_case_is_correct']
    drive_turns=sum(section['turns']['value'] for section in parameters['groups']['drive'])
    current=parameters['groups']['high_voltage'][0]['turns']['value']
    lower=math.ceil(ratio['minimum']*drive_turns)
    nominal=round(ratio['nominal_at_11500v_and_65v_supply']*drive_turns)
    upper=math.floor(ratio['maximum']*drive_turns)
    window=[5e-6,15e-6]
    cases={name:pulse(graph,parameters,turns,window)
           for name,turns in [('current',current),('conditional_lower',lower),
                              ('conditional_nominal',nominal),('conditional_upper',upper)]}
    passed=(current/drive_turns<ratio['minimum']
            and lower<=nominal<=upper
            and all(case['isolated_window_mean_ratio']>0 for case in cases.values())
            and cases['current']['isolated_window_mean_ratio']<ratio['minimum']
            and cases['conditional_nominal']['isolated_window_mean_ratio']>cases['current']['isolated_window_mean_ratio'])
    return dict(format='dac-monitor-t3-hv-ratio-sweep-v1',
        qualification='isolated conditional A5 mismatch diagnostic; no loaded EHT, source-validated winding graph or T3 parameter freeze',
        graph_sha256=sha(GRAPH),parameters_sha256=sha(PARAMETERS),
        design_point_sha256=sha(DESIGN),
        assumed_drive_total_turns=drive_turns,
        conditional_ratio_from_design_point=ratio,
        sample_window_s=window,
        cases=cases,
        pulse_setup='1 V, 16 us pulse across X2:7 to X2:4; each other magnetic terminal shunted by 1 Gohm; isolated HV voltage sampled over 5-15 us',
        finding=f'The active {current:g}/{drive_turns:g}-turn ideal ratio is below the conditional {ratio["minimum"]:.1f}-{ratio["maximum"]:.1f} EHT ratio; the candidate turns sweep only explores that conditional ideal scale.',
        open_checks=['The 64-turn drive winding is an unmeasured hypothesis',
                     'The 60-70 V boost premise, loaded collector pulse and rectified EHT have not been verified',
                     'The X1:3-to-X2:3 return and other T3 tap continuities are unverified',
                     'Open-circuit pulse ratios with 1 Gohm shunts do not establish loaded monitor high voltage'],
        passed=passed)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    report=run();args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(f"current ideal ratio {report['cases']['current']['ideal_open_circuit_ratio']:.3f}; conditional nominal {report['cases']['conditional_nominal']['ideal_open_circuit_ratio']:.3f}; passed={report['passed']}")
    if not report['passed']:raise SystemExit(1)
