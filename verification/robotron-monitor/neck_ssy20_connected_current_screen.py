"""Measure SSY20A current and power in the paired native-video startup."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import neck_ssy20_connected_edge_screen as edge
import steady_supply

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT/'reference/k7222-11/ssy20-connected-current-screen.json'
SOURCE_READ = ROOT/'reference/k7222-11/ssy20-datasheet-direct-read.json'
CURRENT_PROBE = 'i(@q1[ic])'
OLD_SAVE = '.save time v(cathode) v(collector) v(h_hot)'
NEW_SAVE = OLD_SAVE+' @q1[ic]'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate(work, edge_work, ngspice):
    work, edge_work = Path(work), Path(edge_work)
    work.mkdir(parents=True, exist_ok=False)
    for label in ('active','fast_candidate'):
        source = (edge_work/label/'run.cir').read_text()
        if source.count(OLD_SAVE) != 1:
            raise ValueError('paired connected edge deck changed')
        trial = work/label
        trial.mkdir()
        (trial/'run.cir').write_text(source.replace(OLD_SAVE,NEW_SAVE))
        result = subprocess.run([str(ngspice),'-b','-r','trace.raw','-o',
                                 'solver.log','run.cir'],cwd=trial,
                                capture_output=True,text=True,timeout=180)
        if result.returncode or not (trial/'trace.raw').is_file():
            raise ValueError(label+' current solve failed: '
                             +(result.stdout+result.stderr)[-500:])


def summarize_trace(path):
    rows = [row for row in steady_supply.raw_rows(path)
            if row['time'] >= edge.VIDEO_WINDOW_START_S]
    if len(rows) < 75000 or abs(rows[-1]['time']-edge.STOP_S) > 1e-12:
        raise ValueError('connected current trace is incomplete')
    currents = [row[CURRENT_PROBE] for row in rows]
    powers = [max(row['v(collector)'],0)*max(row[CURRENT_PROBE],0)
              for row in rows]
    energy = sum((right['time']-left['time'])*(p_left+p_right)/2
                 for left,right,p_left,p_right in zip(rows,rows[1:],powers,powers[1:]))
    peak_current = max(range(len(rows)),key=lambda i:currents[i])
    peak_power = max(range(len(rows)),key=lambda i:powers[i])
    duration = rows[-1]['time']-rows[0]['time']
    return dict(raw_samples=len(rows),window_s=[rows[0]['time'],rows[-1]['time']],
                collector_current_range_a=[min(currents),max(currents)],
                peak_collector_current_time_s=rows[peak_current]['time'],
                peak_instantaneous_power_w=powers[peak_power],
                peak_instantaneous_power_time_s=rows[peak_power]['time'],
                dissipated_energy_j=energy,mean_power_w=energy/duration)


def analyze(work, edge_work):
    work, edge_work = Path(work), Path(edge_work)
    source = json.loads(SOURCE_READ.read_text())
    limits = source['limits']
    if (limits['ic_a'],limits['ptot_w_at_25c']) != (.6,.7):
        raise ValueError('direct SSY20 current/power source read changed')
    cases = {}
    for label in ('active','fast_candidate'):
        base = (edge_work/label/'run.cir').read_text()
        deck = (work/label/'run.cir').read_text()
        if base.count(OLD_SAVE) != 1 or deck != base.replace(OLD_SAVE,NEW_SAVE):
            raise ValueError(label+' current deck differs beyond added probe')
        trace = work/label/'trace.raw'
        cases[label] = dict(deck_sha256=sha(work/label/'run.cir'),
                            trace_sha256=sha(trace),
                            **summarize_trace(trace))
    return dict(format='dac-monitor-ssy20-connected-current-screen-v1',
                qualification='2 ms conditional native-video startup current/power probe; provisional 19-port T3, manual contrast equivalent, no thermal impedance or pulsed SOA model',
                input_sha256={str(path.relative_to(ROOT)):sha(path)
                              for path in (edge.OUTPUT,SOURCE_READ,
                                           ROOT/'neck_ssy20_connected_edge_screen.py',
                                           ROOT/'steady_supply.py',Path(__file__))},
                work_directory=str(work),edge_work_directory=str(edge_work),
                source_limits=dict(ic_max_a=.6,continuous_ptot_w_at_25c=.7),
                cases=cases,
                both_peak_currents_below_source_max=all(
                    row['collector_current_range_a'][1] < .6 for row in cases.values()),
                both_window_mean_powers_below_continuous_reference=all(
                    row['mean_power_w'] < .7 for row in cases.values()),
                any_instantaneous_power_above_continuous_reference=any(
                    row['peak_instantaneous_power_w'] > .7 for row in cases.values()),
                thermal_or_pulsed_soa_qualified=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True)
    parser.add_argument('--edge-work',type=Path,required=True)
    parser.add_argument('--generate',action='store_true')
    parser.add_argument('--ngspice',type=Path,
                        default=Path(shutil.which('ngspice') or 'ngspice'))
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args=parser.parse_args()
    if args.generate:
        generate(args.work,args.edge_work,args.ngspice)
    report=analyze(args.work,args.edge_work)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print({key:(row['collector_current_range_a'][1],row['peak_instantaneous_power_w'],
                row['mean_power_w']) for key,row in report['cases'].items()})
