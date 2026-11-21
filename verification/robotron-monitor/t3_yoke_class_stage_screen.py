"""Screen paired 31 cm yoke-class windings in the conditional T3 stage."""

import argparse
import hashlib
import json
from pathlib import Path

import page9_centering_compare
import t3_centering_return_screen as centering
import t3_drive_pulse_screen as pulse


ROOT = Path(__file__).resolve().parent
CLASS = ROOT / 'reference/k7222-11/yoke-class-comparator.json'
OUTPUT = ROOT / 'reference/k7222-11/t3-yoke-class-stage-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice):
    source = json.loads(CLASS.read_text())
    comparison = page9_centering_compare.run()
    if not comparison['passed']:
        raise ValueError('page-9 source comparison failed')
    if source['class_scope'] != ('Philips 1987 31 cm, 90-degree, 20 mm-neck, '
                                 '12 kV monochrome deflection units'):
        raise ValueError('catalog class changed; review the yoke transfer')
    rows = source['class_rows']
    if len(rows) != 11 or len({row['type'] for row in rows}) != 11:
        raise ValueError('expected eleven distinct catalog winding pairs')
    inputs = pulse.setup()
    baseline = centering.case(ngspice, inputs, 0, .08)
    cases = []
    for row in rows:
        inductance_h = row['line_inductance_uh'] * 1e-6
        resistance_ohm = row['line_resistance_ohm']
        measured = centering.case(ngspice, inputs, 0, .08,
                                  yoke=(inductance_h, resistance_ohm))
        current = measured['yoke_current_range_a']
        cases.append(dict(catalog_type=row['type'],
                          line_inductance_h=inductance_h,
                          line_resistance_ohm=resistance_ohm,
                          catalog_line_full_scan_app=row['line_full_scan_app'],
                          model_yoke_current_app=current[1] - current[0],
                          **measured))
    by_type = {row['catalog_type']: row for row in cases}
    for first, second in (('AT1077/05', 'AT1077/06'),
                          ('AT1077/15', 'AT1077/23')):
        if by_type[first]['normalized_deck_sha256'] != by_type[second]['normalized_deck_sha256']:
            raise ValueError('equal catalog line windings generated different stages')
    envelope = dict(
        drive_peak_v=[min(row['drive_peak_v'] for row in cases),
                      max(row['drive_peak_v'] for row in cases)],
        eht_at_collector_peak_v=[min(row['eht_at_collector_peak_v'] for row in cases),
                                 max(row['eht_at_collector_peak_v'] for row in cases)],
        model_yoke_current_app=[min(row['model_yoke_current_app'] for row in cases),
                                max(row['model_yoke_current_app'] for row in cases)])
    return dict(
        format='dac-monitor-t3-yoke-class-stage-screen-v1',
        qualification='conditional 4–5 ms prescribed-base stage with unverified T3 graph, E1+E2 centring links and nominal 80 mH chokes; 90-degree catalog class is a sensitivity comparator, not the installed 110-degree AE9VT winding or an A5 turns-ratio qualification',
        source=dict(catalog_url=source['source']['url'],
                    catalog_sha256=source['source']['sha256'],
                    class_scope=source['class_scope'],
                    class_report_sha256=sha(CLASS),
                    centering_source_netlist_sha256=comparison['source_netlist_sha256'],
                    centering_sheet_sha256=comparison['sheet_sha256']),
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (CLASS,
                                    centering.OUTPUT,
                                    ROOT / 't3_centering_return_screen.py',
                                    ROOT / 't3_drive_pulse_screen.py',
                                    ROOT / 't3_yoke_class_stage_screen.py')},
        ngspice_sha256=sha(ngspice),
        fixed_inputs=dict(centering_link_pair='E1+E2',
                          centering_coil_l_h=.08,
                          centering_r4_position=.5,
                          prescribed_base_edge_ns=200,
                          max_step_ns=50),
        active_4mh_yoke_case=baseline,
        class_cases=cases,
        class_case_envelope=envelope,
        class_cases_reaching_11kv_at_collector_peak=sum(
            row['eht_at_collector_peak_v'] >= 11000 for row in cases),
        interpretation='The source-paired class windings change the conditional collector, EHT, X2:4 differential pulse and yoke current substantially from the active 4 mH candidate. This rejects use of the active-stage pulse as a winding-ratio bound across even this limited class comparison. Catalog full-scan currents are for different reference tubes and are listed for context, not used as installed AE9VT acceptance limits. Source-bounded 110-degree/20 mm-neck yoke and T3 data remain needed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['class_cases'])} paired catalog winding cases completed")
