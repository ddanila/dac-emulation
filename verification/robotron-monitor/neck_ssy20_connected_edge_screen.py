"""Compare active and faster neck TF during native-video connected startup."""
import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import time

import neck_ssy20_joint_timing_candidate as fast_candidate
import steady_supply
import transformer_candidates

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT/'examples/phase-a-native-full-text/capture.json.gz'
PROFILE = ROOT/'profiles/k7222-11-neck.json'
MODEL = ROOT/'circuits/k7222-11-neck-models.cir'
OUTPUT = ROOT/'reference/k7222-11/ssy20-connected-edge-screen.json'
CANDIDATE_ID = 't3-fc941ad61c50ce31'
STEP_S = 5e-9
STOP_S = 2e-3
VIDEO_WINDOW_START_S = .001625
PROBES = ('v(cathode)', 'v(collector)', 'v(h_hot)')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(work, ngspice):
    work = Path(work)
    work.mkdir(parents=True, exist_ok=False)
    capture = json.loads(gzip.decompress(ARCHIVE.read_bytes()))
    selection = steady_supply.select(capture)
    if selection['status'] != 'complete':
        raise ValueError('native logical source field is incomplete')
    assembly = steady_supply.assemble(work/'assembly')
    steady_supply.tune(assembly, selection)
    candidate = next((row for row in transformer_candidates.enumerate_candidates(
        assembly['magnetic_graph']) if row['id'] == CANDIDATE_ID), None)
    if candidate is None:
        raise ValueError('conditional T3 candidate changed')
    assembly['contrast_topology'] = 'manual-fig6-equivalent'
    active_tf = json.loads(PROFILE.read_text())['parameters']['q_tf']['nominal']
    for label, tf in (('active', active_tf),
                      ('fast_candidate', fast_candidate.CANDIDATE_TF['nominal'])):
        assembly['parameters']['q_tf'] = tf
        deck, _ = steady_supply.deck(assembly, selection, candidate,
                                     linear_solver='klu', max_step_s=STEP_S,
                                     reltol=.002, abstol=1e-8)
        deck, n = re.subn(r'^\.tran .*$', '.tran 5n 2m 0 5n', deck, flags=re.M)
        if n != 1:
            raise ValueError('connected transient command changed')
        deck, n = re.subn(r'^\.save .*$',
                          '.save time '+ ' '.join(PROBES), deck, flags=re.M)
        if n != 1:
            raise ValueError('connected saved probes changed')
        trial = work/label
        trial.mkdir()
        (trial/'run.cir').write_text(deck)
        start = time.monotonic()
        result = subprocess.run([str(ngspice), '-b', '-r', 'trace.raw',
                                 '-o', 'solver.log', 'run.cir'], cwd=trial,
                                capture_output=True, text=True, timeout=180)
        if result.returncode or not (trial/'trace.raw').is_file():
            raise ValueError(f'{label} connected solve failed after '
                             f'{time.monotonic()-start:.1f}s: '
                             +(result.stdout+result.stderr)[-500:])


def interpolated(rows, position, instant):
    while position+1 < len(rows) and rows[position+1]['time'] < instant:
        position += 1
    if position+1 >= len(rows):
        raise ValueError('connected trace ends before comparison grid')
    left, right = rows[position], rows[position+1]
    fraction = (instant-left['time'])/(right['time']-left['time'])
    return position, {key: left[key]+fraction*(right[key]-left[key])
                      for key in PROBES}


def analyze(work):
    work = Path(work)
    decks = {name:(work/name/'run.cir').read_text()
             for name in ('active','fast_candidate')}
    active_tf = json.loads(PROFILE.read_text())['parameters']['q_tf']['nominal']
    old = f'.param q_tf={active_tf}'
    new = f".param q_tf={fast_candidate.CANDIDATE_TF['nominal']}"
    if (decks['active'].count(old) != 1 or decks['fast_candidate'].count(new) != 1
            or decks['active'].replace(old,new) != decks['fast_candidate']
            or '.tran 5n 2m 0 5n' not in decks['active']):
        raise ValueError('paired decks differ beyond the candidate TF value')
    rows = {name:list(steady_supply.raw_rows(work/name/'trace.raw'))
            for name in decks}
    for name, trace in rows.items():
        if (len(trace) < 40000 or abs(trace[-1]['time']-STOP_S) > 1e-12
                or any(not all(math.isfinite(row[key]) for key in PROBES)
                       for row in trace)):
            raise ValueError(f'{name} connected trace is incomplete')
    count = int((STOP_S-VIDEO_WINDOW_START_S)/STEP_S)+1
    positions = {'active':0,'fast_candidate':0}
    metrics = {key:dict(sum_squared=0.,peak=(0.,None,None,None),
                        active_range=[float('inf'),-float('inf')],
                        fast_range=[float('inf'),-float('inf')]) for key in PROBES}
    for index in range(count):
        instant = VIDEO_WINDOW_START_S+index*STEP_S
        values = {}
        for name in rows:
            positions[name], values[name] = interpolated(rows[name], positions[name], instant)
        for key, metric in metrics.items():
            active, fast = values['active'][key], values['fast_candidate'][key]
            delta = fast-active
            metric['sum_squared'] += delta*delta
            metric['active_range'][0] = min(metric['active_range'][0],active)
            metric['active_range'][1] = max(metric['active_range'][1],active)
            metric['fast_range'][0] = min(metric['fast_range'][0],fast)
            metric['fast_range'][1] = max(metric['fast_range'][1],fast)
            if abs(delta) > metric['peak'][0]:
                metric['peak'] = (abs(delta),instant,active,fast)
    comparison = {key:dict(peak_abs_delta_v=metric['peak'][0],
                           peak_time_s=metric['peak'][1],
                           active_at_peak_v=metric['peak'][2],
                           fast_at_peak_v=metric['peak'][3],
                           rms_delta_v=math.sqrt(metric['sum_squared']/count),
                           active_range_v=metric['active_range'],
                           fast_range_v=metric['fast_range'])
                  for key,metric in metrics.items()}
    if comparison['v(cathode)']['active_range_v'][1]-comparison['v(cathode)']['active_range_v'][0] < 5:
        raise ValueError('selected native video window did not drive the neck')
    return dict(format='dac-monitor-ssy20-connected-edge-screen-v1',
                qualification='2 ms native-logical-input connected startup with provisional 19-port T3 and manual Fig. 6 contrast equivalent; not sustained state or connected transistor SOA qualification',
                input_sha256={str(path.relative_to(ROOT)): sha(path)
                              for path in (ARCHIVE,PROFILE,MODEL,fast_candidate.OUTPUT,
                                           ROOT/'steady_supply.py',
                                           ROOT/'neck_ssy20_joint_timing_candidate.py',
                                           Path(__file__))},
                run_directory=str(work), candidate_id=CANDIDATE_ID,
                contrast_topology='manual-fig6-equivalent',
                max_step_s=STEP_S, comparison_window_s=[VIDEO_WINDOW_START_S,STOP_S],
                common_grid_samples=count,
                active=dict(q_tf_s=active_tf,
                            deck_sha256=sha(work/'active/run.cir'),
                            raw_sha256=sha(work/'active/trace.raw'),
                            raw_samples=len(rows['active'])),
                fast_candidate=dict(q_tf_s=fast_candidate.CANDIDATE_TF['nominal'],
                                    deck_sha256=sha(work/'fast_candidate/run.cir'),
                                    raw_sha256=sha(work/'fast_candidate/trace.raw'),
                                    raw_samples=len(rows['fast_candidate'])),
                comparison=comparison,
                connected_edge_checked=True, connected_stress_qualified=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--generate', action='store_true')
    parser.add_argument('--ngspice', type=Path, default=Path(shutil.which('ngspice') or 'ngspice'))
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.generate:
        generate(args.work,args.ngspice)
    report = analyze(args.work)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('connected cathode peak delta V:',report['comparison']['v(cathode)']['peak_abs_delta_v'])
