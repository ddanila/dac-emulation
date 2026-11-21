"""Screen an angle-matched Philips yoke against the conditional .11 geometry.

The 28.6 mm-neck catalog part is a sensitivity comparator, not AE9VT.
"""

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import yoke_axial_geometry_screen as axial
import yoke_geometry
import yoke_joint_geometry_screen as joint


ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'profiles/k7222-11-yoke-geometry.json'
OLDER_CLASS = ROOT / 'reference/k7222-11/yoke-class-comparator.json'
PDF_SHA256 = '60ac727815c7493e8df4530fb909bc74c35b9120f3eddbdefe7a758bf536e417'
PDF_URL = 'https://bitsavers.trailing-edge.com/components/philips/_dataBooks/1987_T16_Philips_Monochrome_Tubes_and_Deflection_Units.pdf'
REFERENCE = dict(type='AT1039/03', angle_degrees=110, diagonal_mm=310,
                 neck_diameter_mm=28.6, eht_v=17000, scan_width_mm=230,
                 scan_height_mm=170, line_inductance_h=.000228,
                 line_resistance_ohm=.41, line_current_pp_a=7.95,
                 field_inductance_h=.00918, field_resistance_ohm=10.2,
                 field_current_pp_a=1.21, current_tolerance_fraction=.05,
                 line_connection='parallel', field_connection='series')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transferred(reference_current, target_dimension, reference_dimension, eht):
    return reference_current * target_dimension / reference_dimension * math.sqrt(eht / REFERENCE['eht_v'])


def run(source_pdf):
    if sha(source_pdf) != PDF_SHA256:
        raise ValueError('Philips T16 source PDF hash changed')
    older = json.loads(OLDER_CLASS.read_text())
    target = older['target']
    if target != dict(width_mm=210, width_tolerance_mm=20, height_mm=145,
                      height_tolerance_mm=15, eht_v=[11000, 12000]):
        raise ValueError('Robotron picture/EHT targets changed')
    bounds = {}
    nominal = {}
    for axis, current, reference_size, size, spread in (
            ('horizontal', REFERENCE['line_current_pp_a'], REFERENCE['scan_width_mm'],
             target['width_mm'], target['width_tolerance_mm']),
            ('vertical', REFERENCE['field_current_pp_a'], REFERENCE['scan_height_mm'],
             target['height_mm'], target['height_tolerance_mm'])):
        tol = REFERENCE['current_tolerance_fraction']
        bounds[axis] = [transferred(current * (1-tol), size-spread, reference_size, target['eht_v'][0]),
                        transferred(current * (1+tol), size+spread, reference_size, target['eht_v'][1])]
        nominal[axis] = transferred(current, size, reference_size, sum(target['eht_v']) / 2)

    profile = json.loads(PROFILE.read_text())
    profile['neck_radius_m'] = .009
    profile['horizontal']['target_inductance_h'] = REFERENCE['line_inductance_h']
    profile['horizontal']['target_resistance_ohm'] = REFERENCE['line_resistance_ohm']
    profile['vertical']['target_inductance_h'] = REFERENCE['field_inductance_h']
    profile['vertical']['target_resistance_ohm'] = REFERENCE['field_resistance_ohm']
    cases = []
    for screen_m in (.23, .235, .25):
        for field_m in (.02, .025, .0275):
            trial_profile = copy.deepcopy(profile)
            trial_profile['field_length_m'] = field_m
            derived = yoke_geometry.derive(trial_profile)
            line = axial.trial(trial_profile, screen_m, field_m,
                               horizontal_winding=(REFERENCE['line_inductance_h'],
                                                   REFERENCE['line_resistance_ohm']))
            vertical_pp = 2 * joint.vertical_current(derived['field'] | {'screen_z_m': screen_m})
            horizontal_pp = 2 * line['target_current_peak_a'] if line['reaches_210mm_width'] else None
            horizontal_match = horizontal_pp is not None and bounds['horizontal'][0] <= horizontal_pp <= bounds['horizontal'][1]
            vertical_match = bounds['vertical'][0] <= vertical_pp <= bounds['vertical'][1]
            cases.append(dict(screen_z_m=screen_m, common_field_length_m=field_m,
                              horizontal_width_reached=line['reaches_210mm_width'],
                              horizontal_maximum_half_width_m=line['maximum_half_width_m'],
                              horizontal_current_pp_a=horizontal_pp,
                              vertical_current_pp_a=vertical_pp,
                              horizontal_in_own_proxy=horizontal_match,
                              vertical_in_own_proxy=vertical_match,
                              joint_own_proxy_match=horizontal_match and vertical_match))
    if (sum(c['horizontal_width_reached'] for c in cases) != 4
            or sum(c['horizontal_in_own_proxy'] for c in cases) != 1
            or any(c['joint_own_proxy_match'] for c in cases)):
        raise ValueError('angle-matched sensitivity outcome changed')
    return dict(
        format='dac-monitor-yoke-110deg-comparator-v1',
        qualification='cross-neck class sensitivity only; not an installed AE9VT value or geometry freeze',
        source=dict(url=PDF_URL, sha256=PDF_SHA256,
                    selection_guide_printed_page=7,
                    datasheet_printed_pages=[401, 404, 406]),
        input_hashes=dict(profile=sha(PROFILE), older_class=sha(OLDER_CLASS),
                          yoke_geometry=sha(ROOT / 'yoke_geometry.py'),
                          axial_trial=sha(ROOT / 'yoke_axial_geometry_screen.py'),
                          joint_trial=sha(ROOT / 'yoke_joint_geometry_screen.py'),
                          script=sha(Path(__file__))),
        reference=REFERENCE, target=target,
        transfer_equation='I_target_pp = I_reference_pp * target_scan_mm/reference_scan_mm * sqrt(target_EHT/17000 V)',
        transfer_assumptions=['First-order linearized deflection scaling across different CRTs',
                              'Manufacturer +/-5% current tolerance and Robotron picture/EHT windows',
                              'Philips 28.6 mm-neck field shape is not AE9VT or B31G22 geometry'],
        transferred_current_nominal_pp_a=nominal,
        transferred_current_bounds_pp_a=bounds,
        earlier_90deg_family_current_bounds_pp_a=dict(
            horizontal=older['conditional_current_proxy']['line_family_envelope_app'],
            vertical=older['conditional_current_proxy']['field_family_envelope_app']),
        geometry_assumptions=dict(inner_neck_radius_m=.009, screen_z_m=[.23, .235, .25],
                                  common_field_length_m=[.02, .025, .0275],
                                  catalog_electrical_windings=True,
                                  remaining_magnetic_geometry_from='profiles/k7222-11-yoke-geometry.json'),
        cases=cases,
        horizontal_width_reached_count=sum(c['horizontal_width_reached'] for c in cases),
        horizontal_own_proxy_match_count=sum(c['horizontal_in_own_proxy'] for c in cases),
        joint_own_proxy_match_count=sum(c['joint_own_proxy_match'] for c in cases),
        interpretation='The 110-degree comparator permits more horizontal current than the earlier 90-degree family envelope, but no sampled common-field geometry meets both its own horizontal and vertical transferred-current bounds. Its 28.6 mm neck prevents using it as an installed AE9VT bound.',
        unresolved=['Installed AE9VT winding and axis-specific field extent are unsourced',
                    'B31G22 gun-to-screen distance and inner neck radius are unsourced'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['joint_own_proxy_match_count']}/{len(result['cases'])} joint matches")
