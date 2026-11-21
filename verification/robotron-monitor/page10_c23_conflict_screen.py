"""Compare the page-10 C23 scan connection with the manual Fig. 12 connection.

This is an A1 topology-sensitivity check, not a sustained vertical-stage score.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import reference


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page10-feedback-source-netlist.json'
PROFILE = ROOT / 'profiles/k7222-11-vertical-output.json'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
PDF_DIR = ROOT.parent.parent / 'build/monitor/phase-a/sources'
STOP = .16
STEP = 1e-5
PROBES = {'tp7_y2_v': 'feedback', 'tp8_y1_v': 'output',
          'yoke_a': 'yoke', 'a2_reference_v': 'reference'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    source = json.loads(SOURCE.read_text())
    conflict, = source['source_conflicts']
    if sha(PDF_DIR / source['source']['file']) != source['source']['pdf_sha256']:
        raise ValueError('page-10 source PDF changed')
    if sha(PDF_DIR / conflict['operation_manual_file']) != conflict['operation_manual_pdf_sha256']:
        raise ValueError('operation manual PDF changed')
    profile = json.loads(PROFILE.read_text())
    period = profile['parameters']['sync_period']['nominal']
    with tempfile.TemporaryDirectory() as tmp:
        directory = Path(tmp)
        base_dir, scan_dir = directory / 'manual', directory / 'scan'
        base = reference.run(PROFILE, base_dir, stop=STOP, step=STEP)
        deck = (base_dir / 'run.cir').read_text()
        original = 'C706 vertical_reference 0 2.2u\n'
        alternate = 'C706 n16 0 2.2u\n'
        if deck.count(original) != 1 or alternate in deck:
            raise ValueError('unexpected C23 source connection in stage deck')
        scan_dir.mkdir()
        scan_deck = deck.replace(original, alternate, 1)
        (scan_dir / 'run.cir').write_text(scan_deck)
        with (scan_dir / 'ngspice.log').open('w') as log:
            subprocess.run(['ngspice', '-n', '-b', 'run.cir'], cwd=scan_dir,
                           stdout=log, stderr=subprocess.STDOUT, check=True)
        if re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix',
                     (scan_dir / 'ngspice.log').read_text()):
            raise ValueError('scan-connection solver diagnostics rejected')
        probes = base['probes']
        manual_rows = reference.read_samples(base_dir / 'samples.txt', probes, 0, STOP, STEP)
        scan_rows = reference.read_samples(scan_dir / 'samples.txt', probes, 0, STOP, STEP)
        if len(manual_rows) != len(scan_rows):
            raise ValueError('different sample counts')
        window_start = STOP - 2 * period
        paired = [(m, s) for m, s in zip(manual_rows, scan_rows)
                  if m[0] >= window_start]
        if len(paired) != round(2 * period / STEP):
            raise ValueError('incomplete final two-field comparison')
        if any(abs(m[0] - s[0]) > 1e-10 for m, s in paired):
            raise ValueError('misaligned topology samples')
        metrics = {}
        samples_per_field = round(period / STEP)
        for label, name in PROBES.items():
            index = 1 + next(i for i, probe in enumerate(probes) if probe['name'] == name)
            a = [m[index] for m, _ in paired]
            b = [s[index] for _, s in paired]
            span = max(a) - min(a)
            scale = max(abs(sum(a) / len(a)), span, 1e-12)
            delta = max(abs(x - y) for x, y in zip(a, b))
            repeat_error = max(abs(x - y) for x, y in zip(
                a[:samples_per_field], a[samples_per_field:2 * samples_per_field]))
            metrics[label] = {'manual_swing': span, 'scan_swing': max(b) - min(b),
                              'max_pointwise_difference': delta,
                              'difference_fraction_of_manual_scale': delta / scale,
                              'manual_field_repeat_fraction_of_swing': repeat_error / max(span, 1e-12)}
        sensitivity_pass = all(value['difference_fraction_of_manual_scale'] < .02
                               for value in metrics.values())
        return {
            'format': 'dac-monitor-page10-c23-conflict-screen-v1',
            'qualification': 'A1 topology-sensitivity only; synthetic sync, ideal rails, '
                             'provisional device models, final two fields not certified periodic',
            'inputs': {'page10_source_read_sha256': sha(SOURCE),
                       'page10_pdf_sha256': source['source']['pdf_sha256'],
                       'operation_manual_pdf_sha256': conflict['operation_manual_pdf_sha256'],
                       'profile_sha256': sha(PROFILE), 'sheet_sha256': sha(SHEET),
                       'script_sha256': sha(__file__),
                       'manual_deck_sha256': base['hashes']['deck'],
                       'scan_deck_sha256': hashlib.sha256(scan_deck.encode()).hexdigest()},
            'comparison': {'stop_s': STOP, 'sample_step_s': STEP,
                           'final_two_field_start_s': window_start,
                           'paired_final_rows': len(paired),
                           'manual_connection': original.strip(),
                           'scan_connection': alternate.strip(),
                           'max_difference_over_each_manual_mean_or_swing': metrics,
                           'all_selected_probes_below_two_percent': sensitivity_pass},
            'decision': {'selected': 'manual-fig12-reference-connection',
                         'basis': 'The operating manual names the constant A2 reference '
                                  'as the R59/R60/C23 source; the schematic scan instead '
                                  'joins C23 to A3 pin 6. The paired topology screen checks '
                                  'that this conflict does not materially change the current '
                                  'stage bench under the A1 two-percent sensitivity rule.',
                         'phase_b_qualified': False},
        }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    raise SystemExit(0 if result['comparison']['all_selected_probes_below_two_percent'] else 2)
