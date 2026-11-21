"""Test whether the paired Brimar TBY7 currents fit reduced tube geometry."""

import argparse
import hashlib
import json
from pathlib import Path

import trajectory
import yoke_brimar_110deg_comparator as brimar
import yoke_geometry


ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'profiles/k7222-11-yoke-geometry.json'
OUTPUT = ROOT / 'reference/k7222-11/yoke-brimar-geometry-screen.json'
SCREENS_M = (.23, .24, .25)
COMMON_FIELDS_M = (.020, .025, .0275)
TARGET_HALF_M = dict(horizontal=.105, vertical=.0725)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def paired_profile(catalog_row, *, length_m, horizontal_radius_m=.016):
    profile = json.loads(PROFILE.read_text())
    profile['neck_radius_m'] = .009
    profile['field_length_m'] = length_m
    profile['horizontal']['sheet_radius_m'] = horizontal_radius_m
    for axis, prefix in (('horizontal', 'line'), ('vertical', 'field')):
        profile[axis]['target_inductance_h'] = catalog_row[prefix+'_inductance_h']
        profile[axis]['target_resistance_ohm'] = catalog_row[prefix+'_resistance_ohm']
    return profile


def axis_check(field, screen_m, axis, bounds_pp_a):
    diagnostic = field | {'screen_z_m': screen_m,
                          'screen_width_m': .35, 'screen_height_m': .25}
    def ray(current):
        result = trajectory.ray(11500, 350, 4000,
                                current if axis == 'horizontal' else 0,
                                current if axis == 'vertical' else 0,
                                overrides=diagnostic, step_m=.0002)
        coordinate = 'x_m' if axis == 'horizontal' else 'y_m'
        return result['reason'], result.get(coordinate)
    low, high = (ray(current/2) for current in bounds_pp_a)
    target = TARGET_HALF_M[axis]
    bracketed = (low[0] == high[0] == 'screen' and
                 low[1] <= target <= high[1])
    result = dict(bound_current_pp_a=bounds_pp_a,
                  lower_bound_ray=dict(reason=low[0], half_extent_m=low[1]),
                  upper_bound_ray=dict(reason=high[0], half_extent_m=high[1]),
                  target_half_extent_m=target, target_bracketed=bracketed)
    if bracketed:
        a, b = (current/2 for current in bounds_pp_a)
        for _ in range(25):
            mid = (a+b)/2
            reason, extent = ray(mid)
            if reason != 'screen':
                raise ValueError('target bracket lost to aperture')
            if extent < target:
                a = mid
            else:
                b = mid
        result['required_current_pp_a'] = a+b
    return result


def run(source_pdf):
    catalog = brimar.run(source_pdf)
    if json.loads(brimar.OUTPUT.read_text()) != catalog:
        raise ValueError('saved Brimar comparator differs from manufacturer source')
    tby7 = next(row for row in catalog['class_cases'] if row['type'] == 'TBY7')
    rows = []
    for screen in SCREENS_M:
        for length in COMMON_FIELDS_M:
            profile = paired_profile(tby7, length_m=length)
            derived = yoke_geometry.derive(profile)
            axes = {axis: axis_check(derived['field'], screen, axis,
                                    tby7['transferred_current_bounds_pp_a'][axis])
                    for axis in ('horizontal', 'vertical')}
            rows.append(dict(screen_z_m=screen, common_field_length_m=length,
                             inner_neck_radius_m=.009,
                             horizontal_sheet_radius_m=.016,
                             winding_fill_fraction={axis: derived['axes'][axis]['fill_fraction']
                                                    for axis in axes},
                             axes=axes,
                             joint_current_match=all(row['target_bracketed']
                                                     for row in axes.values())))
    # This diagnostic deliberately tests a tighter horizontal sheet and
    # separate axial field lengths without changing the active trajectory.
    # Orthogonal single-axis rays are only a separable first-order comparison.
    edge = dict(screen_z_m=.25, horizontal_field_length_m=.025,
                vertical_field_length_m=.035, horizontal_sheet_radius_m=.0136,
                inner_neck_radius_m=.009)
    edge_axes = {}
    for axis, length in (('horizontal', edge['horizontal_field_length_m']),
                         ('vertical', edge['vertical_field_length_m'])):
        profile = paired_profile(tby7, length_m=length,
                                 horizontal_radius_m=edge['horizontal_sheet_radius_m'])
        derived = yoke_geometry.derive(profile)
        edge_axes[axis] = axis_check(derived['field'], edge['screen_z_m'], axis,
                                     tby7['transferred_current_bounds_pp_a'][axis])
    edge['axes'] = edge_axes
    edge['separable_joint_current_match'] = all(
        result['target_bracketed'] for result in edge_axes.values())
    return dict(
        format='dac-monitor-yoke-brimar-geometry-screen-v1',
        qualification='conditional reduced-ray class sensitivity; no installed B31G22/AE9VT field or geometry identification',
        source=catalog['source'],
        input_hashes={str(path.relative_to(ROOT)): sha(path)
                      for path in (brimar.OUTPUT, PROFILE, ROOT/'trajectory.py',
                                   ROOT/'yoke_geometry.py', Path(__file__))},
        catalog_type='TBY7',
        declared_assumptions=dict(anode_v=11500, grid2_v=350, focus_v=4000,
                                  field_start_m=.075, inner_neck_radius_m=.009,
                                  single_axis_rays=True,
                                  target_half_width_m=.105,
                                  target_half_height_m=.0725,
                                  source_picture_current_bounds_are_transferred_proxies=True),
        common_field_cases=rows,
        common_field_joint_matches=sum(row['joint_current_match'] for row in rows),
        axis_specific_edge_case=edge,
        interpretation='The paired TBY7 winding fits the reduced magnetic winding pack, but none of the nine sampled common-field geometries reaches both Robotron half-extents within its transferred current bounds. A tighter 13.6 mm horizontal sheet and different 25/35 mm axis lengths can bracket both targets only at a 250 mm gun-to-screen path, an upper-edge sensitivity case for the 253 mm B31-G overall-length outline. This does not establish the installed field profile or a physically plausible gun position; do not promote it to the active design point.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{report['common_field_joint_matches']}/{len(report['common_field_cases'])} common-field matches; edge scenario {report['axis_specific_edge_case']['separable_joint_current_match']}")
