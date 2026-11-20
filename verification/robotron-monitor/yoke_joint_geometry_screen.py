"""Check whether one short-field geometry can meet both yoke current proxies."""

import argparse
import hashlib
import json
from pathlib import Path

import trajectory
import yoke_axial_geometry_screen as axial
import yoke_geometry
import yoke_neck_clearance_screen as neck


ROOT = Path(__file__).resolve().parent
TARGET_HALF_HEIGHT_M = .0725
SCREENS_M = (.23, .235, .25)
FIELDS_M = (.020, .025, .0275)
INNER_NECK_RADIUS_M = .009


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def vertical_current(field, anode_v=11500):
    diagnostic = field | {'screen_height_m': .25}

    def height(current):
        ray = trajectory.ray(anode_v, 350, 4000, 0, current,
                             overrides=diagnostic, step_m=.0002)
        if ray['reason'] != 'screen':
            raise ValueError('vertical ray clips before the target height')
        return ray['y_m']

    low, high = 0., .01
    while height(high) < TARGET_HALF_HEIGHT_M:
        low, high = high, high + .01
        if high > .8:
            raise ValueError('vertical target not reached below 0.8 A peak')
    for _ in range(25):
        mid = (low + high) / 2
        if height(mid) < TARGET_HALF_HEIGHT_M:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def run(older_pdf, outline_gif):
    if sha(older_pdf) != axial.OLDER_SHA or sha(outline_gif) != axial.OUTLINE_SHA:
        raise ValueError('source scan or B31-G outline changed')
    profile = json.loads(neck.PROFILE.read_text())
    yoke_class = json.loads(neck.YOKE_CLASS.read_text())
    references = [next(row for row in yoke_class['class_rows'] if row['type'] == name)
                  for name in ('AT1077/05', 'AT1077/06')]
    if [(row['line_inductance_uh'], row['line_resistance_ohm'],
         row['field_inductance_mh'], row['field_resistance_ohm'])
            for row in references] != [(475, .8, 18, 10), (475, .8, 72, 40)]:
        raise ValueError('Philips reference windings changed')
    current_class = yoke_class['conditional_current_proxy']
    line_proxy = current_class['line_family_envelope_app']
    field_proxy = current_class['field_family_envelope_app']
    profile['neck_radius_m'] = INNER_NECK_RADIUS_M
    profile['horizontal']['target_inductance_h'] = .000475
    profile['horizontal']['target_resistance_ohm'] = .8
    rows = []
    for reference in references:
        profile['vertical']['target_inductance_h'] = reference['field_inductance_mh'] * 1e-3
        profile['vertical']['target_resistance_ohm'] = reference['field_resistance_ohm']
        for screen_m in SCREENS_M:
            for field_m in FIELDS_M:
                profile['field_length_m'] = field_m
                derived = yoke_geometry.derive(profile)
                magnetic = derived['field'] | {'screen_z_m': screen_m}
                line = axial.trial(profile, screen_m, field_m)
                vertical_peak = vertical_current(magnetic)
                line_in_proxy = (line['reaches_210mm_width'] and
                                 line_proxy[0] <= line['target_current_pp_a'] <= line_proxy[1])
                field_in_proxy = field_proxy[0] <= 2*vertical_peak <= field_proxy[1]
                rows.append(dict(reference_yoke=reference['type'],
                                 screen_z_m=screen_m, common_field_length_m=field_m,
                                 inner_neck_radius_m=INNER_NECK_RADIUS_M,
                                 horizontal_maximum_half_width_m=line['maximum_half_width_m'],
                                 horizontal_width_reached=line['reaches_210mm_width'],
                                 horizontal_peak_current_a=line.get('target_current_peak_a'),
                                 horizontal_in_class_proxy=line_in_proxy,
                                 vertical_peak_current_a=vertical_peak,
                                 vertical_current_pp_a=2*vertical_peak,
                                 vertical_in_class_proxy=field_in_proxy,
                                 joint_proxy_match=line_in_proxy and field_in_proxy))
    index = {(row['reference_yoke'], row['screen_z_m'], row['common_field_length_m']): row for row in rows}
    if (not index[('AT1077/05', .235, .020)]['horizontal_in_class_proxy']
            or index[('AT1077/05', .235, .020)]['vertical_in_class_proxy']
            or not index[('AT1077/06', .235, .020)]['joint_proxy_match']
            or index[('AT1077/06', .23, .025)]['horizontal_width_reached']):
        raise ValueError('joint yoke comparison changed')
    return dict(
        format='dac-monitor-yoke-joint-geometry-screen-v1',
        qualification='conditional common-field reduced-ray comparison; Philips 90-degree yoke is not installed AE9VT',
        sources=dict(k7222_11_page18=dict(file='older.pdf', sha256=axial.OLDER_SHA, page=18,
                                         reading='B31G22 tube and AE9VT 6802.01 yoke'),
                     b31_g_outline=dict(url='https://elektroncso.hu/cikkek/crt_m31.gif',
                                       retrieved_copy_sha256=axial.OUTLINE_SHA,
                                       reading='B31-G outside neck diameter near 20 mm and maximum overall length 253 mm'),
                     philips_comparator=dict(url=yoke_class['source']['url'],
                                             sha256=yoke_class['source']['sha256'],
                                             types=['AT1077/05', 'AT1077/06'],
                                             printed_pages=[449, 450, 453, 454],
                                             scope=yoke_class['class_scope'])),
        input_hashes={'profiles/k7222-11-yoke-geometry.json': sha(neck.PROFILE),
                      'reference/k7222-11/yoke-class-comparator.json': sha(neck.YOKE_CLASS),
                      'trajectory.py': sha(ROOT/'trajectory.py'),
                      'yoke_geometry.py': sha(ROOT/'yoke_geometry.py'),
                      'yoke_axial_geometry_screen.py': sha(ROOT/'yoke_axial_geometry_screen.py'),
                      'yoke_joint_geometry_screen.py': sha(Path(__file__))},
        assumptions=dict(common_axial_field_for_both_axes=True,
                         inner_neck_radius_m=INNER_NECK_RADIUS_M,
                         target_picture_width_m=.210, target_picture_height_m=.145,
                         anode_v=11500, grid2_v=350, focus_v=4000,
                         reference_windings=references),
        conditional_current_proxies_app=dict(horizontal=line_proxy, vertical=field_proxy),
        cases=rows, joint_proxy_matches=sum(row['joint_proxy_match'] for row in rows),
        interpretation='At 235 mm path, 9 mm inner radius and 20 mm common field, horizontal full width needs about 5.71 A peak-to-peak inside the 90-degree proxy. The AT1077/05 18 mH/10 ohm field winding needs about 1.00 A peak-to-peak above its 0.73 A family proxy, while the AT1077/06 72 mH/40 ohm variant needs about 0.50 A and gives a conditional joint match. These class variants are not AE9VT; they demonstrate that field winding choice changes whether a common-field fallback is feasible.',
        unresolved=['An AE9VT winding and axis-specific axial field profile are not sourced',
                    'The installed B31G22 gun location and inner neck radius remain unknown',
                    'The active common 40 mm field, 280 mm path and 10 mm aperture cannot be frozen as physical geometry'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--older-pdf', type=Path, required=True)
    parser.add_argument('--outline-gif', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.older_pdf, args.outline_gif)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{result['joint_proxy_matches']}/{len(result['cases'])} joint proxy matches")
