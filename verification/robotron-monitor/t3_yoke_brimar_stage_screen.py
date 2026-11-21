"""Screen the paired 20 mm-neck Brimar class in the conditional T3 stage."""

import argparse
import hashlib
import json
from pathlib import Path

import page9_centering_compare
import t3_centering_return_screen as centering
import t3_drive_pulse_screen as pulse
import yoke_brimar_110deg_comparator as brimar


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-yoke-brimar-stage-screen.json'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(ngspice, source_pdf):
    if sha(source_pdf) != brimar.PDF_SHA256:
        raise ValueError('Brimar manufacturer PDF hash changed')
    comparison = page9_centering_compare.run()
    if not comparison['passed']:
        raise ValueError('page-9 centring source comparison failed')
    catalog = brimar.run(source_pdf)
    if json.loads(brimar.OUTPUT.read_text()) != catalog:
        raise ValueError('saved Brimar comparator differs from current source')
    inputs = pulse.setup()
    baseline = centering.case(ngspice, inputs, 0, .08)
    cases = []
    for row in catalog['class_cases']:
        observed = centering.case(
            ngspice, inputs, 0, .08,
            yoke=(row['line_inductance_h'], row['line_resistance_ohm']))
        current = observed['yoke_current_range_a']
        cases.append(dict(catalog_type=row['type'],
                          line_inductance_h=row['line_inductance_h'],
                          line_resistance_ohm=row['line_resistance_ohm'],
                          catalog_transferred_current_bounds_pp_a=(
                              row['transferred_current_bounds_pp_a']['horizontal']),
                          model_yoke_current_pp_a=current[1] - current[0],
                          **observed))
    envelope = {key: [min(row[key] for row in cases),
                      max(row[key] for row in cases)]
                for key in ('drive_peak_v', 'eht_at_collector_peak_v',
                            'model_yoke_current_pp_a')}
    return dict(
        format='dac-monitor-t3-yoke-brimar-stage-screen-v1',
        qualification='conditional 4–5 ms prescribed-base stage, not a periodic operating point or installed AE9VT winding; T3 graph and centring links unverified',
        source=dict(url=brimar.PDF_URL, sha256=brimar.PDF_SHA256,
                    centering_source_netlist_sha256=comparison['source_netlist_sha256']),
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (brimar.OUTPUT, centering.OUTPUT,
                                    ROOT / 't3_centering_return_screen.py',
                                    ROOT / 't3_drive_pulse_screen.py',
                                    ROOT / 'yoke_brimar_110deg_comparator.py',
                                    ROOT / 't3_yoke_brimar_stage_screen.py')},
        ngspice_sha256=sha(ngspice),
        fixed_inputs=dict(centering_link_pair='E1+E2',
                          centering_coil_l_h=.08,
                          centering_r4_position=.5,
                          prescribed_base_edge_ns=200,
                          max_step_ns=50),
        active_4mh_yoke_case=baseline,
        class_cases=cases,
        class_case_envelope=envelope,
        class_cases_in_11_12kv_band_at_collector_peak=sum(
            11000 <= row['eht_at_collector_peak_v'] <= 12000 for row in cases),
        interpretation='The source-paired 31 cm/110-degree/20 mm-neck class tests the present T3 stage more directly than the 28.6 mm catalog family. Conditional pulse and EHT shifts still cannot determine the installed winding or A5 turns ratios without source-qualified X2:4 drive and return bounds.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.ngspice, args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['class_cases'])} 20 mm-neck catalog cases completed")
