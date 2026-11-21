"""Screen source-paired 110-degree catalog yokes in the conditional T3 stage."""

import argparse
import hashlib
import json
from pathlib import Path

import page9_centering_compare
import t3_centering_return_screen as centering
import t3_drive_pulse_screen as pulse
import yoke_110deg_comparator


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-yoke-110deg-stage-screen.json'
PHILIPS = yoke_110deg_comparator.PDF_SHA256
MULLARD = '668b1f6cf9a11b21b83f8d62ae9401aa62d390630366316511471a28e230aa1a'
MULLARD_URL = 'https://bms.isjtr.ro/other/Mullard/Mullard_QuickReferenceGuide_Part1_1985.pdf'

# Philips T16 1987 selection guide, printed p. 7: line windings are paired
# electrical values, not independent extrema. All use a 28.6 mm neck.
ROWS = (
    ('AT1039/03', 31, 'landscape', 228, .41, 7.95),
    ('AT1039/21', 36, 'landscape', 205, .33, 7.64),
    ('AT1039/00', 38, 'portrait', 225, .39, 5.60),
    ('AT1038/42', 38, 'landscape', 700, 1.03, 4.12),
    ('AT1039/01', 38, 'landscape', 206, .36, 7.20),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, philips_pdf, mullard_pdf):
    if sha(philips_pdf) != PHILIPS or sha(mullard_pdf) != MULLARD:
        raise ValueError('manufacturer catalog PDF hash changed')
    comparison = page9_centering_compare.run()
    if not comparison['passed']:
        raise ValueError('page-9 centring source comparison failed')
    closest = yoke_110deg_comparator.REFERENCE
    if (closest['type'], closest['line_inductance_h'], closest['line_resistance_ohm'],
            closest['line_current_pp_a']) != ('AT1039/03', .000228, .41, 7.95):
        raise ValueError('closest 31 cm comparator changed')
    inputs = pulse.setup()
    baseline = centering.case(ngspice, inputs, 0, .08)
    cases = []
    for name, diagonal_cm, orientation, inductance_uh, resistance_ohm, current_app in ROWS:
        measured = centering.case(ngspice, inputs, 0, .08,
                                  yoke=(inductance_uh * 1e-6, resistance_ohm))
        current = measured['yoke_current_range_a']
        cases.append(dict(catalog_type=name, reference_diagonal_cm=diagonal_cm,
                          orientation=orientation, neck_diameter_mm=28.6,
                          catalog_note=('flat square application' if name == 'AT1039/21'
                                        else None),
                          line_inductance_h=inductance_uh * 1e-6,
                          line_resistance_ohm=resistance_ohm,
                          catalog_full_scan_app_at_17kv=current_app,
                          model_yoke_current_app=current[1] - current[0],
                          **measured))
    envelope = {key: [min(row[key] for row in cases), max(row[key] for row in cases)]
                for key in ('drive_peak_v', 'eht_at_collector_peak_v',
                            'model_yoke_current_app')}
    conflicting_resistance = centering.case(ngspice, inputs, 0, .08,
                                           yoke=(.000228, .14))
    detailed = next(row for row in cases if row['catalog_type'] == 'AT1039/03')
    return dict(
        format='dac-monitor-t3-yoke-110deg-stage-screen-v1',
        qualification='conditional 4–5 ms prescribed-base stage; 110-degree/28.6 mm-neck catalog class is not the installed 20 mm-neck AE9VT, and the T3 graph and centring links remain unverified',
        source=dict(philips_url=yoke_110deg_comparator.PDF_URL,
                    philips_sha256=PHILIPS,
                    philips_selection_guide_printed_page=7,
                    mullard_url=MULLARD, mullard_sha256=MULLARD,
                    mullard_pdf_page=134, mullard_printed_page=132,
                    mullard_at1039_03_line_resistance_ohm=.14,
                    philips_at1039_03_line_resistance_ohm=.41,
                    discrepancy_resolution='The older Mullard quick-reference table prints 0.14 ohm for AT1039/03 parallel line coils, while the later Philips T16 selection guide and detailed AT1039/03 sheet print 0.41 ohm. The screen uses the detailed 1987 value; neither source identifies AE9VT.',
                    centering_source_netlist_sha256=comparison['source_netlist_sha256']),
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (centering.OUTPUT,
                                    ROOT / 't3_centering_return_screen.py',
                                    ROOT / 't3_drive_pulse_screen.py',
                                    ROOT / 'yoke_110deg_comparator.py',
                                    ROOT / 't3_yoke_110deg_stage_screen.py')},
        ngspice_sha256=sha(ngspice),
        fixed_inputs=dict(centering_link_pair='E1+E2',
                          centering_coil_l_h=.08,
                          centering_r4_position=.5,
                          prescribed_base_edge_ns=200,
                          max_step_ns=50),
        active_4mh_yoke_case=baseline,
        class_cases=cases,
        at1039_03_quick_guide_resistance_case=conflicting_resistance,
        at1039_03_resistance_discrepancy_effect=dict(
            drive_peak_difference_v=conflicting_resistance['drive_peak_v'] - detailed['drive_peak_v'],
            eht_at_collector_peak_difference_v=(
                conflicting_resistance['eht_at_collector_peak_v'] -
                detailed['eht_at_collector_peak_v'])),
        class_case_envelope=envelope,
        class_cases_reaching_11kv_at_collector_peak=sum(
            row['eht_at_collector_peak_v'] >= 11000 for row in cases),
        class_cases_in_11_12kv_band_at_collector_peak=sum(
            11000 <= row['eht_at_collector_peak_v'] <= 12000 for row in cases),
        interpretation='The angle-matched catalog windings show conditional T3 drive, EHT and yoke-current sensitivity under the same assumed transformer. The 31 cm AT1039/03 is the closest catalog row by screen size but still has a 28.6 mm neck and 17 kV reference; the others are 36–38 cm. These results constrain neither the installed AE9VT winding nor a T3 turns ratio.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--philips-pdf', type=Path, required=True)
    parser.add_argument('--mullard-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.philips_pdf, args.mullard_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['class_cases'])} angle-matched catalog cases completed")
