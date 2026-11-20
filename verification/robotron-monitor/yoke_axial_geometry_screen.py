"""Screen the assumed yoke field length against a shorter 110-degree tube class.

This is a sensitivity study, not an identification of the B31G22 or AE9VT.
"""
import argparse
import hashlib
import json
from pathlib import Path

import trajectory
import yoke_geometry


ROOT = Path(__file__).resolve().parent
PROFILE = ROOT/'profiles/k7222-11-yoke-geometry.json'
YOKE_CLASS = ROOT/'reference/k7222-11/yoke-class-comparator.json'
PHILIPS_SHA = '60ac727815c7493e8df4530fb909bc74c35b9120f3eddbdefe7a758bf536e417'
ROBOTRON_SHA = '887787a48f36e84ce92edbd39acf2469e6a64f755e22d12d80f687f376f492a6'
TARGET_HALF_WIDTH_M = .105


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def trial(profile, screen_m, field_m):
    trial_profile = json.loads(json.dumps(profile))
    trial_profile['field_length_m'] = field_m
    trial_profile['horizontal']['target_inductance_h'] = .000475
    trial_profile['horizontal']['target_resistance_ohm'] = .8
    derived = yoke_geometry.derive(trial_profile)
    field = derived['field'] | {'screen_z_m': screen_m, 'screen_width_m': .35}

    def ray(current):
        return trajectory.ray(11500, 350, 4000, current, 0,
                              overrides=field, step_m=.0002)

    low, high = 0., 4.
    if ray(high)['reason'] != 'neck aperture':
        raise ValueError('4 A did not bracket neck clipping')
    for _ in range(30):
        mid = (low+high)/2
        if ray(mid)['reason'] == 'neck aperture':
            high = mid
        else:
            low = mid
    clip = low
    at_clip = ray(clip)
    if at_clip['reason'] != 'screen':
        raise ValueError('neck-limit ray did not land on comparison screen')
    maximum = at_clip['x_m']
    result = dict(screen_z_m=screen_m, field_length_m=field_m,
                  maximum_half_width_m=maximum,
                  neck_clip_current_a=clip,
                  reaches_210mm_width=maximum >= TARGET_HALF_WIDTH_M,
                  horizontal_tesla_per_amp=field['horizontal_tesla_per_amp'],
                  horizontal_inductance_h=derived['electrical']['yoke_horizontal_l'],
                  horizontal_resistance_ohm=derived['electrical']['yoke_horizontal_r'])
    if result['reaches_210mm_width']:
        lower, upper = 0., clip
        for _ in range(30):
            mid = (lower+upper)/2
            impact = ray(mid)
            if impact['reason'] != 'screen':
                raise ValueError('ray clipped below the neck limit')
            if impact['x_m'] < TARGET_HALF_WIDTH_M:
                lower = mid
            else:
                upper = mid
        required = (lower+upper)/2
        result['target_current_peak_a'] = required
        result['target_current_pp_a'] = 2*required
        result['neck_clip_margin_fraction'] = (clip-required)/clip
    return result


def longest_field_for_width(profile, screen_m, passing_m, failing_m):
    if (not trial(profile, screen_m, passing_m)['reaches_210mm_width']
            or trial(profile, screen_m, failing_m)['reaches_210mm_width']):
        raise ValueError('field-length threshold is not bracketed')
    low, high = passing_m, failing_m
    for _ in range(12):
        mid = (low+high)/2
        if trial(profile, screen_m, mid)['reaches_210mm_width']:
            low = mid
        else:
            high = mid
    return dict(screen_z_m=screen_m, maximum_field_length_m=low,
                first_failing_field_length_m=high,
                method='bisection of maximum width before neck clipping')


def run(philips_pdf, robotron_pdf):
    if sha(philips_pdf) != PHILIPS_SHA or sha(robotron_pdf) != ROBOTRON_SHA:
        raise ValueError('manufacturer PDF provenance changed')
    profile = json.loads(PROFILE.read_text())
    yoke_class = json.loads(YOKE_CLASS.read_text())
    if (yoke_class['reference_scan_at1077_05']['width_mm'] != 257
            or yoke_class['target']['width_mm'] != 210):
        raise ValueError('class scan reference or target changed')
    cases = [trial(profile, screen, field)
             for screen, field in ((.28, .04), (.28, .0347),
                                   (.23, .0347), (.23, .025),
                                   (.20, .025), (.20, .020))]
    current_class = yoke_class['conditional_current_proxy']['line_family_envelope_app']
    for row in cases:
        if row['reaches_210mm_width']:
            row['inside_90_degree_yoke_current_proxy'] = (
                current_class[0] <= row['target_current_pp_a'] <= current_class[1])
    index = {(row['screen_z_m'], row['field_length_m']): row for row in cases}
    if (index[(.28, .0347)]['reaches_210mm_width'] is not True
            or index[(.23, .0347)]['reaches_210mm_width'] is not False
            or index[(.23, .025)]['reaches_210mm_width'] is not True
            or index[(.20, .020)]['reaches_210mm_width'] is not True):
        raise ValueError('axial sensitivity changed')
    thresholds = [longest_field_for_width(profile, screen, passing, failing)
                  for screen, passing, failing in ((.23, .025, .0347),
                                                   (.20, .020, .025))]
    return dict(
        format='dac-monitor-yoke-axial-geometry-screen-v1',
        qualification='110-degree tube-class and reduced-ray sensitivity only; not installed B31G22/AE9VT geometry or a calibrated current',
        sources={
            'philips_t16': dict(url='https://bitsavers.trailing-edge.com/components/philips/_dataBooks/1987_T16_Philips_Monochrome_Tubes_and_Deflection_Units.pdf',
                                sha256=PHILIPS_SHA, type='A31-410W',
                                printed_pages=[43, 45],
                                reading='31 cm, 110-degree, 20 mm neck; maximum overall tube length 233 mm'),
            'robotron_cross_revision': dict(url='https://www.sax.de/~zander/zubehoer/k7222/k7222_61.pdf',
                                             sha256=ROBOTRON_SHA,
                                             revision='K7222.13/23, August 1984, section 5.7',
                                             reading='Horizontal stage with AE9VT is designed for a 110-degree tube',
                                             limitation='Not a K7222.11 mechanical drawing'),
        },
        source_hashes={'profiles/k7222-11-yoke-geometry.json': sha(PROFILE),
                       'reference/k7222-11/yoke-class-comparator.json': sha(YOKE_CLASS),
                       'trajectory.py': sha(ROOT/'trajectory.py'),
                       'yoke_geometry.py': sha(ROOT/'yoke_geometry.py'),
                       'yoke_axial_geometry_screen.py': sha(Path(__file__))},
        class_comparison=dict(maximum_overall_length_m=.233,
                              active_gun_to_screen_m=trajectory.DEFAULTS['screen_z_m'],
                              nominal_screen_proxy_m=.23,
                              argument='Any gun-to-screen distance in the A31-410W must be shorter than its 233 mm maximum overall length; this does not bound the B31G22 or locate its gun, so 230 mm is an upper-edge sensitivity case rather than a nominal tube dimension.'),
        held_assumptions=dict(yoke_start_m=profile['field_start_m'],
                              neck_radius_m=profile['neck_radius_m'],
                              line_winding='Philips AT1077/05 class 475 uH, 0.8 ohm',
                              anode_v=11500, grid2_v=350, focus_v=4000,
                              picture_half_width_m=TARGET_HALF_WIDTH_M),
        line_current_comparator_app=current_class,
        cases=cases,
        conditional_field_length_thresholds=thresholds,
        interpretation='At 230 mm gun-to-screen, the earlier 34.7 mm field fails before 210 mm width; a 25 mm field reaches the width at about 2.64 A peak with 4.4% neck-current margin, within the broad 90-degree yoke current proxy. At 200 mm, a 25 mm field fails and a 20 mm field reaches at 3.37 A peak, above that proxy. These are coupled geometry sensitivities, not a sourced field length or installed current.',
        unresolved=['B31G22 gun location, inside neck aperture and screen curvature',
                    'AE9VT axial field profile, electrical winding and sensitivity',
                    'Whether the 110-degree K7222.13/23 tube class transfers to K7222.11'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--philips-pdf', type=Path, required=True)
    parser.add_argument('--robotron-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.philips_pdf, args.robotron_pdf)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('axial geometry cases:', len(report['cases']))


if __name__ == '__main__':
    main()
