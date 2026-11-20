"""Compare the provisional AE9VT yoke with a cited 31 cm monitor-yoke class.

The current scaling is a first-order magnetic-deflection transfer, not an
identification of the installed yoke or a connected-stage calibration.
"""
import argparse
import copy
import hashlib
import json
import math
from pathlib import Path

import yoke_geometry
import trajectory

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / 'profiles/k7222-11-yoke-geometry.json'
TARGETS = ROOT / 'reference/k7222-11/service-observations.json'
DESIGN = ROOT / 'reference/k7222-11/design-point.json'
PDF_SHA256 = '60ac727815c7493e8df4530fb909bc74c35b9120f3eddbdefe7a758bf536e417'
PDF_URL = 'https://bitsavers.trailing-edge.com/components/philips/_dataBooks/1987_T16_Philips_Monochrome_Tubes_and_Deflection_Units.pdf'

# Philips T16 (1987), selection guide p. 6: 31 cm, 90-degree, 20 mm neck,
# 12 kV rows. Full-scan current is peak-to-peak at each maker's reference tube.
# The AT1077/05 data sheet, pp. 449-450, also prints its 257 x 195 mm
# edge-to-edge scan dimensions and +/-5% current/electrical tolerances.
CLASS_ROWS = [
    ('AT1077/05', 475, .80, 18, 10, 2.9, .485),
    ('AT1077/06', 475, .80, 72, 40, 2.9, .24),
    ('AT1077/07', 118, .22, 18, 10, 5.8, .48),
    ('AT1077/15', 240, .42, 12.5, 7.25, 4.2, .60),
    ('AT1077/16', 170, .35, 6.6, 4.35, 4.92, .80),
    ('AT1077/20', 145, .25, 18, 10, 5.3, .50),
    ('AT1077/22', 112, .20, 7.7, 4.15, 6.1, .74),
    ('AT1077/23', 240, .42, 31, 16.6, 4.2, .37),
    ('AT1078/01', 310, .66, 23.8, 13.6, 3.4, .48),
    ('AT1078/02', 480, .90, 18, 11.5, 2.96, .52),
    ('AT1078/19', 245, .53, 6.85, 4.10, 3.9, .85),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def current_proxy(reference_app, target_mm, reference_mm, target_eht_v):
    return reference_app * target_mm / reference_mm * math.sqrt(target_eht_v / 12000)


def geometry_trial(source_profile, length_m, target_half_width_m):
    profile = copy.deepcopy(source_profile)
    profile['field_length_m'] = length_m
    profile['horizontal']['target_inductance_h'] = .000475
    profile['horizontal']['target_resistance_ohm'] = .8
    model = yoke_geometry.derive(profile)
    field = model['field'] | {'screen_width_m': .35}

    def ray(current):
        return trajectory.ray(11500, 350, 4000, current, 0,
                              overrides=field, step_m=.0002)

    low, high = 0., .25
    while ray(high)['reason'] != 'neck aperture':
        low, high = high, high * 2
        if high > 8:
            raise ValueError('no neck-aperture limit within 8 A')
    for _ in range(28):
        mid = (low + high) / 2
        if ray(mid)['reason'] == 'neck aperture':
            high = mid
        else:
            low = mid
    limit = low
    edge = ray(limit)
    if edge['reason'] != 'screen':
        raise ValueError('neck-limit ray did not reach screen')
    maximum = edge['x_m']
    result = dict(field_length_m=length_m,
                  class_winding_inductance_h=model['electrical']['yoke_horizontal_l'],
                  class_winding_resistance_ohm=model['electrical']['yoke_horizontal_r'],
                  horizontal_tesla_per_amp=field['horizontal_tesla_per_amp'],
                  effective_turns=model['axes']['horizontal']['turns'],
                  winding_fill_fraction=model['axes']['horizontal']['fill_fraction'],
                  maximum_current_before_neck_clip_a=limit,
                  maximum_reachable_half_width_m=maximum,
                  required_half_width_m=target_half_width_m,
                  reaches_target=maximum >= target_half_width_m)
    if result['reaches_target']:
        lower, upper = 0., limit
        for _ in range(28):
            mid = (lower + upper) / 2
            observation = ray(mid)
            if observation['reason'] != 'screen':
                raise ValueError('unexpected ray loss below neck limit')
            if observation['x_m'] < target_half_width_m:
                lower = mid
            else:
                upper = mid
        current = (lower + upper) / 2
        result['current_for_target_half_width_a'] = current
        result['neck_clip_current_margin_a'] = limit - current
        result['neck_clip_current_margin_fraction'] = (limit - current) / limit
    return result


def run(source_pdf):
    if sha(source_pdf) != PDF_SHA256:
        raise ValueError('Philips T16 source PDF hash changed')
    targets = {row['quantity']: row for row in json.loads(TARGETS.read_text())['manual_targets']}
    width, height = targets['picture_width'], targets['picture_height']
    if (width['value'], width['tolerance'], height['value'], height['tolerance']) != (210, 20, 145, 15):
        raise ValueError('manual picture-size target changed')
    design = json.loads(DESIGN.read_text())
    eht = design['high_voltage_ratio']['eht_target_v']
    if (eht['minimum'], eht['maximum']) != (11000, 12000):
        raise ValueError('manual EHT range changed')
    geometry = yoke_geometry.read(PROFILE)
    source_profile = json.loads(PROFILE.read_text())
    rows = [dict(type=name, line_inductance_uh=lh, line_resistance_ohm=rh,
                 field_inductance_mh=lv, field_resistance_ohm=rv,
                 line_full_scan_app=ih, field_full_scan_app=iv)
            for name, lh, rh, lv, rv, ih, iv in CLASS_ROWS]
    family = {key: [min(row[key] for row in rows), max(row[key] for row in rows)]
              for key in ('line_inductance_uh', 'line_resistance_ohm',
                          'field_inductance_mh', 'field_resistance_ohm',
                          'line_full_scan_app', 'field_full_scan_app')}
    family_si = dict(line_inductance_h=[round(v * 1e-6, 9) for v in family['line_inductance_uh']],
                     line_resistance_ohm=family['line_resistance_ohm'],
                     field_inductance_h=[round(v * 1e-3, 7) for v in family['field_inductance_mh']],
                     field_resistance_ohm=family['field_resistance_ohm'])
    nominal_eht = (eht['minimum'] + eht['maximum']) / 2
    proxy = {
        'line_nominal_at1077_05_app': current_proxy(2.9, width['value'], 257, nominal_eht),
        'field_nominal_at1077_05_app': current_proxy(.485, height['value'], 195, nominal_eht),
        'line_family_envelope_app': [
            current_proxy(family['line_full_scan_app'][0] * .95,
                          width['value'] - width['tolerance'], 257, eht['minimum']),
            current_proxy(family['line_full_scan_app'][1] * 1.05,
                          width['value'] + width['tolerance'], 257, eht['maximum'])],
        'field_family_envelope_app': [
            current_proxy(family['field_full_scan_app'][0] * .95,
                          height['value'] - height['tolerance'], 195, eht['minimum']),
            current_proxy(family['field_full_scan_app'][1] * 1.05,
                          height['value'] + height['tolerance'], 195, eht['maximum'])],
    }
    active = dict(line_inductance_uh=geometry['electrical']['yoke_horizontal_l'] * 1e6,
                  line_resistance_ohm=geometry['electrical']['yoke_horizontal_r'],
                  field_inductance_mh=geometry['electrical']['yoke_vertical_l'] * 1e3,
                  field_resistance_ohm=geometry['electrical']['yoke_vertical_r'])
    comparison = {key: dict(active=active[key], family_range=family[key],
                            inside_family=family[key][0] <= active[key] <= family[key][1])
                  for key in active}
    trials = [geometry_trial(source_profile, length, width['value'] / 2000)
              for length in (source_profile['field_length_m'], .0347)]
    if trials[0]['reaches_target'] or not trials[1]['reaches_target']:
        raise ValueError('class yoke geometry trial outcome changed')
    return dict(format='dac-monitor-yoke-class-comparator-v1',
                qualification='class-typical comparison and conditional current proxy; not installed AE9VT values or a geometry freeze',
                source=dict(url=PDF_URL, sha256=PDF_SHA256,
                            selection_guide_printed_page=6,
                            at1077_05_data_printed_pages=[449, 450]),
                inputs_sha256=dict(profile=sha(PROFILE), targets=sha(TARGETS), design=sha(DESIGN)),
                class_scope='Philips 1987 31 cm, 90-degree, 20 mm-neck, 12 kV monochrome deflection units',
                class_rows=rows, class_envelope=family, class_envelope_si=family_si,
                reference_scan_at1077_05=dict(width_mm=257, height_mm=195,
                                               eht_v=12000, current_tolerance_fraction=.05),
                target=dict(width_mm=width['value'], width_tolerance_mm=width['tolerance'],
                            height_mm=height['value'], height_tolerance_mm=height['tolerance'],
                            eht_v=[eht['minimum'], eht['maximum']]),
                proxy_equation='I_target_pp = I_reference_pp * target_scan_mm / reference_scan_mm * sqrt(target_EHT / 12000 V)',
                proxy_assumptions=['Small-angle linearized deflection transfer between tubes and yokes',
                                   'The AT1077/05 257 x 195 mm scan is a reference scale for all class rows',
                                   'Family extrema and AT1077/05 +/-5% sensitivity bracket class transfer; not factory AE9VT limits'],
                conditional_current_proxy=proxy, active_geometry_electrical_comparison=comparison,
                class_winding_geometry_trials=trials,
                conclusion='The active 4 mH/2 ohm horizontal yoke lies above the cited 0.112-0.480 mH/0.20-0.90 ohm family; the active 20 mH/10 ohm vertical yoke is inside its 6.6-72 mH/4.10-40 ohm spread. A 475 uH/0.8 ohm class winding still clips at 90.87 mm half-width with the 40 mm field. The 34.7 mm field reaches 105 mm only 0.46% below the assumed neck-clip current. The family current proxy is not an installed-yoke current target.',
                next_step='Bound the inner neck aperture and axial field extent before selecting the narrow 34.7 mm geometry; preserve the original AE9VT identity as unresolved.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('horizontal class match:', report['active_geometry_electrical_comparison']['line_inductance_uh']['inside_family'])


if __name__ == '__main__':
    main()
