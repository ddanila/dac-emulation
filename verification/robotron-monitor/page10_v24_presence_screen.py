"""Compare provisional vertical stage with and without V24/D736."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import reference

ROOT = Path(__file__).resolve().parent
WORKTREE = ROOT.parent.parent
SOURCE = ROOT / 'reference/k7222-11/page10-v24-source-conflict.json'
REPORT = ROOT / 'reference/k7222-11/page10-v24-presence-screen.json'
PROFILE = ROOT / 'profiles/k7222-11-vertical-output.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
STOP = .16
STEP = 1e-5
PROBES = {'tp7_y2_v': 'feedback', 'tp8_y1_v': 'output',
          'yoke_a': 'yoke', 'a2_reference_v': 'reference'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    source = json.loads(SOURCE.read_text())
    if source['format'] != 'dac-monitor-page10-v24-source-conflict-v1':
        raise ValueError('V24 source record changed')
    if (sha(WORKTREE / 'build/monitor/phase-a/sources/older.pdf')
            != source['board_schematic']['pdf_sha256']
            or sha(WORKTREE / 'build/monitor/phase-a/page10-600.png')
            != source['board_schematic']['full_page_600dpi_sha256']
            or sha(WORKTREE / 'build/monitor/phase-a/page10-feedback-bottom-1200-crop.png')
            != source['board_schematic']['feedback_crop_1200dpi_sha256']
            or sha(WORKTREE / 'build/monitor/phase-a/page15-600.png')
            != source['parts_list']['view_600dpi_sha256']
            or sha(WORKTREE / 'build/monitor/phase-a/sources/older-operation.pdf')
            != source['operation_manual']['pdf_sha256']
            or sha(WORKTREE / 'build/monitor/phase-a/operation-fig12-page15-600.png')
            != source['operation_manual']['view_600dpi_sha256']):
        raise ValueError('V24 source PDF or view changed')
    period = json.loads(PROFILE.read_text())['parameters']['sync_period']['nominal']
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        present_dir, omitted_dir = root / 'present', root / 'omitted'
        base = reference.run(PROFILE, present_dir, stop=STOP, step=STEP)
        deck = (present_dir / 'run.cir').read_text()
        line = source['active_model'] + '\n'
        if deck.count(line) != 1:
            raise ValueError('V24 line missing or duplicated in stage deck')
        candidate = deck.replace(line, '', 1)
        omitted_dir.mkdir()
        (omitted_dir / 'run.cir').write_text(candidate)
        with (omitted_dir / 'ngspice.log').open('w') as log:
            subprocess.run(['ngspice', '-n', '-b', 'run.cir'], cwd=omitted_dir,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix',
                     (omitted_dir / 'ngspice.log').read_text()):
            raise ValueError('V24-omitted solver diagnostics rejected')
        probes = base['probes']
        present = reference.read_samples(present_dir / 'samples.txt', probes, 0, STOP, STEP)
        omitted = reference.read_samples(omitted_dir / 'samples.txt', probes, 0, STOP, STEP)
        if len(present) != len(omitted):
            raise ValueError('different stage sample counts')
        window_start = STOP - 2 * period
        paired = [(a, b) for a, b in zip(present, omitted) if a[0] >= window_start]
        if len(paired) != round(2 * period / STEP):
            raise ValueError('incomplete final two-field window')
        if any(abs(a[0] - b[0]) > 1e-10 for a, b in paired):
            raise ValueError('stage samples misaligned')
        metrics = {}
        for label, name in PROBES.items():
            index = 1 + next(i for i, probe in enumerate(probes) if probe['name'] == name)
            a = [row[index] for row, _ in paired]
            b = [row[index] for _, row in paired]
            span = max(a) - min(a)
            scale = max(abs(sum(a) / len(a)), span, 1e-12)
            delta = max(abs(x-y) for x, y in zip(a, b))
            metrics[label] = {'present_swing': span,
                              'omitted_swing': max(b) - min(b),
                              'max_pointwise_difference': delta,
                              'difference_fraction_of_present_mean_or_swing': delta / scale}
        return {
            'format': 'dac-monitor-page10-v24-presence-screen-v1',
            'qualification': 'Provisional 160 ms synthetic-sync ideal-rail stage, final two-field paired topology screen; not a settled or installed-board score',
            'inputs': {'source_conflict_sha256': sha(SOURCE),
                       'profile_sha256': sha(PROFILE), 'sheet_sha256': sha(SHEET),
                       'script_sha256': sha(__file__),
                       'present_deck_sha256': base['hashes']['deck'],
                       'omitted_deck_sha256': hashlib.sha256(candidate.encode()).hexdigest()},
            'comparison': {'stop_s': STOP, 'sample_step_s': STEP,
                           'final_two_field_start_s': window_start,
                           'paired_final_rows': len(paired),
                           'present_line': line.strip(),
                           'omitted_change': 'delete exactly the present_line',
                           'metrics': metrics,
                           'all_selected_probes_below_two_percent': all(
                               value['difference_fraction_of_present_mean_or_swing'] < .02
                               for value in metrics.values())},
            'decision': {'selected': 'manual-and-parts-list-present-V24',
                         'basis': 'Fig. 12 and the printed parts list include V24; the board-schematic feedback crop does not visibly locate it. The paired screen bounds the current stage consequence of omitting it but cannot establish installed wiring.',
                         'phase_b_qualified': False},
        }


if __name__ == '__main__':
    result = run()
    REPORT.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: round(value['difference_fraction_of_present_mean_or_swing'], 5)
                      for key, value in result['comparison']['metrics'].items()}))
