"""Screen B31-G outside-neck diameter against the assumed inner aperture."""

import argparse
import hashlib
import json
from pathlib import Path

import trajectory
import yoke_axial_geometry_screen as axial


ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'profiles/k7222-11-yoke-geometry.json'
YOKE_CLASS = ROOT / 'reference/k7222-11/yoke-class-comparator.json'
OUTSIDE_NECK_RADIUS_M = .010
RADII_M = (.010, .0095, .009, .0085)
GEOMETRIES_M = ((.25, .0275), (.23, .025), (.25, .020),
                (.23, .020), (.20, .020))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def case(profile, screen_m, field_m, radius_m, current_class):
    varied = json.loads(json.dumps(profile))
    varied['neck_radius_m'] = radius_m
    row = axial.trial(varied, screen_m, field_m)
    if row['reaches_210mm_width']:
        row['inside_90_degree_current_proxy'] = (
            current_class[0] <= row['target_current_pp_a'] <= current_class[1])
    row['inner_neck_radius_m'] = radius_m
    row['hypothetical_glass_wall_m'] = OUTSIDE_NECK_RADIUS_M - radius_m
    return row


def minimum_inner_radius(profile, screen_m, field_m, current_class):
    low, high = .005, .010
    if case(profile, screen_m, field_m, low, current_class)['reaches_210mm_width']:
        return dict(screen_z_m=screen_m, field_length_m=field_m,
                    minimum_inner_radius_m_at_or_below=.005,
                    qualification='threshold is below the scanned 5 mm lower endpoint')
    if not case(profile, screen_m, field_m, high, current_class)['reaches_210mm_width']:
        raise ValueError('10 mm radius does not bracket a passing case')
    for _ in range(10):
        mid = (low + high) / 2
        if case(profile, screen_m, field_m, mid, current_class)['reaches_210mm_width']:
            high = mid
        else:
            low = mid
    return dict(screen_z_m=screen_m, field_length_m=field_m,
                last_failing_inner_radius_m=low,
                first_passing_inner_radius_m=high,
                maximum_hypothetical_wall_thickness_m=OUTSIDE_NECK_RADIUS_M-high,
                method='bisection of 210 mm reduced-ray width at neck clip')


def run(older_pdf, outline_gif):
    if sha(older_pdf) != axial.OLDER_SHA or sha(outline_gif) != axial.OUTLINE_SHA:
        raise ValueError('source scan or B31-G outline changed')
    profile = json.loads(PROFILE.read_text())
    if profile['neck_radius_m'] != OUTSIDE_NECK_RADIUS_M or trajectory.DEFAULTS['neck_radius_m'] != OUTSIDE_NECK_RADIUS_M:
        raise ValueError('active 10 mm inner-aperture premise changed')
    yoke_class = json.loads(YOKE_CLASS.read_text())
    current_class = yoke_class['conditional_current_proxy']['line_family_envelope_app']
    rows = [case(profile, screen, field, radius, current_class)
            for screen, field in GEOMETRIES_M for radius in RADII_M]
    index = {(row['screen_z_m'], row['field_length_m'], row['inner_neck_radius_m']): row
             for row in rows}
    if (index[(.23, .025, .009)]['reaches_210mm_width']
            or not index[(.23, .020, .009)]['reaches_210mm_width']
            or not index[(.25, .020, .0085)]['reaches_210mm_width']):
        raise ValueError('neck-radius sensitivity changed')
    thresholds = [minimum_inner_radius(profile, screen, field, current_class)
                  for screen, field in GEOMETRIES_M]
    return dict(
        format='dac-monitor-yoke-neck-clearance-screen-v1',
        qualification='outside-neck drawing and reduced-ray sensitivity only; hypothetical inner apertures, not measured B31G22 glass wall or AE9VT field',
        sources=dict(
            k7222_11_page18=dict(file='older.pdf', sha256=axial.OLDER_SHA, page=18,
                                 reading='Installed B31G22 tube and AE9VT 6802.01 yoke'),
            b31_g_family_outline=dict(url='https://elektroncso.hu/cikkek/crt_m31.gif',
                                      retrieved_copy_sha256=axial.OUTLINE_SHA,
                                      reading='B31-G neck outside diameter near 20 mm and maximum overall length 253 mm',
                                      limitation='Drawing edition and installed B31G22 glass dimensions are not established')),
        input_hashes={'profiles/k7222-11-yoke-geometry.json': sha(PROFILE),
                      'reference/k7222-11/yoke-class-comparator.json': sha(YOKE_CLASS),
                      'trajectory.py': sha(ROOT / 'trajectory.py'),
                      'yoke_geometry.py': sha(ROOT / 'yoke_geometry.py'),
                      'yoke_axial_geometry_screen.py': sha(ROOT / 'yoke_axial_geometry_screen.py'),
                      'yoke_neck_clearance_screen.py': sha(Path(__file__))},
        geometric_rule='Inner neck radius must be smaller than outside radius; the active 10 mm inner radius equals the outline\'s approximately 10 mm outside radius and implies zero wall in that nominal comparison. It cannot be accepted as a physical B31G22 profile without better dimensions.',
        active_inner_neck_radius_m=profile['neck_radius_m'],
        hypothetical_inner_radii_m=RADII_M,
        held_conditions=dict(anode_v=11500, grid2_v=350, focus_v=4000,
                             yoke_start_m=profile['field_start_m'],
                             line_winding='Philips AT1077/05 class 475 uH, 0.8 ohm',
                             picture_half_width_m=axial.TARGET_HALF_WIDTH_M),
        line_current_comparator_app=current_class,
        cases=rows, boundary_estimates=thresholds,
        interpretation='At the 230 mm/25 mm axial case, 9.5 mm inner radius still reaches 210 mm width but 9 mm does not. Shortening the field to 20 mm restores width at 9 mm for a 230 mm screen proxy, though its 5.84 A peak-to-peak current is just above the broad 90-degree yoke proxy. At 250 mm/20 mm, an 8.5 mm inner radius reaches width within that proxy. None of these cases fixes the installed geometry.',
        unresolved=['B31G22 exact outside and inside neck dimensions, gun location and screen curvature',
                    'AE9VT field start, axial extent, sensitivity and actual electrical current envelope',
                    'The active 280 mm gun-to-screen path and 10 mm inner neck radius still require replacement with a bounded physical profile'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--older-pdf', type=Path, required=True)
    parser.add_argument('--outline-gif', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.older_pdf, args.outline_gif)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['cases'])} neck-clearance cases")
