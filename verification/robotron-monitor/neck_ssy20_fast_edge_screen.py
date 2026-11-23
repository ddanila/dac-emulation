"""Compare active and faster SSY20A neck proxy on a 5 ns isolated-stage grid."""
import argparse
import hashlib
import json
from pathlib import Path

import neck_ssy20_joint_timing_candidate as candidate
import reference

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT/'profiles/k7222-11-neck.json'
MODEL = ROOT/'circuits/k7222-11-neck-models.cir'
OUTPUT = ROOT/'reference/k7222-11/ssy20-fast-edge-screen.json'
STEP_S = 5e-9
STOP_S = 4e-4


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(runtime, directory):
    runtime, directory = Path(runtime), Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    profile = reference.read_profile(PROFILE)
    probes = profile['probes']
    names = [probe['name'] for probe in probes]
    reports = {}
    samples = {}
    for label, changes in (('active', {}),
                           ('fast_candidate', {'q_tf': candidate.CANDIDATE_TF['nominal']})):
        trial = directory/label
        reports[label] = reference.run(PROFILE, trial, stop=STOP_S, step=STEP_S,
                                       changes=changes, runtime=runtime)
        samples[label] = reference.read_samples(trial/'samples.txt', probes,
                                                0, STOP_S, STEP_S)
    active, fast = samples['active'], samples['fast_candidate']
    if (len(active) != 80001 or len(fast) != len(active)
            or any(abs(a[0]-b[0]) > 1e-12 for a,b in zip(active,fast))):
        raise ValueError('paired 5 ns neck samples are not aligned')
    comparison = {}
    for name in ('collector', 'cathode', 'intensity', 'grid1', 'grid2'):
        index = names.index(name)+1
        peak = max(((abs(a[index]-b[index]), a[0], a[index], b[index])
                    for a,b in zip(active,fast)), key=lambda row: row[0])
        late = max(abs(a[index]-b[index]) for a,b in zip(active,fast)
                   if a[0] >= .0003)
        coarse = max(abs(active[i][index]-fast[i][index])
                     for i in range(0,len(active),40) if active[i][0] >= .0003)
        comparison[name] = dict(peak_delta_v=peak[0], peak_time_s=peak[1],
                                active_at_peak_v=peak[2], fast_at_peak_v=peak[3],
                                late_peak_delta_v=late,
                                late_200ns_grid_peak_delta_v=coarse)
    return dict(format='dac-monitor-ssy20-fast-edge-screen-v1',
                qualification='isolated synthetic neck bench at 5 ns sample spacing; not connected CRT stress, native video drive or an A2 qualification',
                input_sha256={str(path.relative_to(ROOT)): sha(path)
                              for path in (PROFILE, MODEL, candidate.OUTPUT,
                                           ROOT/'circuits/k7222-11-neck-bench.cir',
                                           ROOT/'circuits/k7222-11-neck.kicad_sch',
                                           ROOT/'neck_ssy20_joint_timing_candidate.py',
                                           ROOT/'reference.py',Path(__file__))},
                runtime_path=str(runtime), run_directory=str(directory),
                step_s=STEP_S, stop_s=STOP_S, sample_count=len(active),
                active=dict(deck_sha256=reports['active']['hashes']['deck'],
                            samples_sha256=sha(directory/'active/samples.txt')),
                fast_candidate=dict(q_tf_s=candidate.CANDIDATE_TF['nominal'],
                                    deck_sha256=reports['fast_candidate']['hashes']['deck'],
                                    samples_sha256=sha(directory/'fast_candidate/samples.txt')),
                comparison=comparison,
                connected_stress_checked=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--run-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.runtime, args.run_directory)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print('cathode peak delta V:',report['comparison']['cathode']['peak_delta_v'])
