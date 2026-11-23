"""Recheck the 39–43 V TBY7 rail cases with the corrected X2:10/X2:13 nets."""
import argparse
import hashlib
import json
from pathlib import Path

import t3_brimar_rail_boundary_screen as rail
import t3_drive_pulse_screen as pulse

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
OUTPUT = REF / 't3-brimar-corrected-rail-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, source_pdf):
    if sha(source_pdf) != rail.SOURCE_PDF_SHA:
        raise ValueError('K7222.11 source PDF changed')
    catalog = json.loads(rail.CATALOG.read_text())
    stage = json.loads(rail.STAGE.read_text())
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    winding = (tby7['line_inductance_h'], tby7['line_resistance_ohm'])
    inputs = pulse.setup()
    cases = [rail.rail_case(ngspice, inputs, feed, winding)
             for feed in (39., 41., 43.)]
    saved = next(row for row in stage['class_cases'] if row['catalog_type'] == 'TBY7')
    if (abs(cases[1]['yoke_current_pp_a'] - saved['model_yoke_current_pp_a']) > 1e-6
            or abs(cases[1]['eht_at_collector_peak_v'] - saved['eht_at_collector_peak_v']) > .01):
        raise ValueError('41 V corrected rail case differs from current TBY7 stage')
    lower = tby7['transferred_current_bounds_pp_a']['horizontal'][0]
    if not all(case['yoke_current_pp_a'] < lower for case in cases):
        raise ValueError('one corrected rail case reaches the class current boundary')
    return dict(format='dac-monitor-t3-brimar-corrected-rail-screen-v1',
                qualification='conditional prescribed-base stage with corrected external X2:10/X2:13 nets; legacy T3 magnetic graph remains unqualified',
                input_hashes={str(path.relative_to(ROOT)): sha(path)
                              for path in (rail.CATALOG, rail.STAGE,
                                           ROOT/'reference/k7222-11/horizontal-output-transcription.json',
                                           ROOT/'t3_brimar_rail_boundary_screen.py',
                                           ROOT/'t3_drive_pulse_screen.py', Path(__file__))},
                source_pdf_sha256=sha(source_pdf), ngspice_sha256=sha(ngspice),
                tby7_class_lower_current_pp_a=lower,
                cases=[{key: case[key] for key in ('feed_v', 'r5_equivalent_position',
                       'yoke_current_pp_a', 'eht_at_collector_peak_v',
                       'normalized_deck_sha256')} for case in cases],
                class_current_reached=False,
                interpretation='Across the source-derived 39–43 V rail span, the corrected-pin conditional stage remains below the transferred TBY7 current boundary and far below the 11–12 kV EHT target; the former 42.504 V crossing is not reproducible.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print([(row['feed_v'], row['yoke_current_pp_a'], row['eht_at_collector_peak_v'])
           for row in report['cases']])
