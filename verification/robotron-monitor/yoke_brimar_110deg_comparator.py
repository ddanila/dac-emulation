"""Transfer Brimar's 31 cm/110-degree/20 mm-neck yoke class to .11 targets."""

import argparse
import hashlib
import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/yoke-brimar-110deg-comparator.json'
TARGET = ROOT / 'reference/k7222-11/yoke-class-comparator.json'
PDF_URL = ('https://tubedata.altanatubes.com.br/other/Brimar/'
           'Brimar_IndustrialCathodeRayTubes_DataSection_Issue3.pdf')
PDF_SHA256 = 'eb327b3bde53b62472190bd1fd968bc8b1687a082ed991bc0adc0b836801ae01'

# Brimar Industrial Cathode Ray Tubes, selection table p. 8 and individual
# TBY3/TBY5/TBY7 scan-coil sheets p. 1. M31-120 is a 31 cm, 110-degree,
# 20.7 mm maximum-neck tube; the coils fit a nominal 20 mm neck. The maker's
# raster-distortion figure is 235 x 165 mm, used only as a transfer proxy.
ROWS = (
    ('TBY3', .000258, .55, .030, 16.7, 5.1, .53),
    ('TBY5', .000258, .55, .007, 3.1, 5.1, 1.16),
    ('TBY7', .0041, 8.8, .032, 16.0, 1.3, .5),
)
REFERENCE = dict(tube='M31-120', tube_diagonal_cm=31,
                 tube_deflection_degrees=110, tube_maximum_neck_mm=20.7,
                 yoke_nominal_neck_mm=20, tube_maximum_overall_length_mm=233,
                 reference_eht_v=11000, proxy_raster_width_mm=235,
                 proxy_raster_height_mm=165)
TRANSFER_SPREAD = .10  # declared class-transfer uncertainty, not maker tolerance


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def transfer(current, target_mm, reference_mm, eht_v):
    return current * target_mm / reference_mm * math.sqrt(eht_v / REFERENCE['reference_eht_v'])


def run(source_pdf):
    if sha(source_pdf) != PDF_SHA256:
        raise ValueError('Brimar manufacturer PDF hash changed')
    target = json.loads(TARGET.read_text())['target']
    if target != dict(width_mm=210, width_tolerance_mm=20, height_mm=145,
                      height_tolerance_mm=15, eht_v=[11000, 12000]):
        raise ValueError('Robotron picture/EHT targets changed')
    rows = []
    for name, lh, rh, lv, rv, ih, iv in ROWS:
        nominal = dict(horizontal=transfer(ih, target['width_mm'],
                                           REFERENCE['proxy_raster_width_mm'], 11500),
                       vertical=transfer(iv, target['height_mm'],
                                         REFERENCE['proxy_raster_height_mm'], 11500))
        bounds = dict(
            horizontal=[transfer(ih * (1-TRANSFER_SPREAD),
                                 target['width_mm']-target['width_tolerance_mm'],
                                 REFERENCE['proxy_raster_width_mm'], 11000),
                        transfer(ih * (1+TRANSFER_SPREAD),
                                 target['width_mm']+target['width_tolerance_mm'],
                                 REFERENCE['proxy_raster_width_mm'], 12000)],
            vertical=[transfer(iv * (1-TRANSFER_SPREAD),
                               target['height_mm']-target['height_tolerance_mm'],
                               REFERENCE['proxy_raster_height_mm'], 11000),
                      transfer(iv * (1+TRANSFER_SPREAD),
                               target['height_mm']+target['height_tolerance_mm'],
                               REFERENCE['proxy_raster_height_mm'], 12000)])
        rows.append(dict(type=name, line_inductance_h=lh,
                         line_resistance_ohm=rh, field_inductance_h=lv,
                         field_resistance_ohm=rv,
                         maker_full_scan_current_pp_a=dict(horizontal=ih, vertical=iv),
                         transferred_current_nominal_pp_a=nominal,
                         transferred_current_bounds_pp_a=bounds))
    envelope = {axis: [min(row['transferred_current_bounds_pp_a'][axis][0]
                           for row in rows),
                       max(row['transferred_current_bounds_pp_a'][axis][1]
                           for row in rows)] for axis in ('horizontal', 'vertical')}
    return dict(
        format='dac-monitor-yoke-brimar-110deg-comparator-v1',
        qualification='source-paired 31 cm/110-degree/20 mm-neck class transfer; not AE9VT identification, B31G22 geometry, or a freeze',
        source=dict(url=PDF_URL, sha256=PDF_SHA256,
                    selection_table_printed_page=8,
                    scan_coil_sheets='TBY3/TBY5/TBY7 page 1'),
        input_hashes=dict(target=sha(TARGET), script=sha(__file__)),
        reference=REFERENCE, target=target,
        transfer_equation='I_target_pp = I_M31-120_pp * target_scan_mm/Brimar_235x165mm_raster_mm * sqrt(target_EHT/11000V)',
        transfer_uncertainty_fraction=TRANSFER_SPREAD,
        transfer_uncertainty_basis='Declared +/-10% model-transfer allowance; Brimar states 5%/8% inductance tolerance, not full-scan current tolerance. The 235 x 165 mm raster-distortion figure is a size proxy, not a guaranteed full-scan specification.',
        class_cases=rows, transferred_current_envelope_pp_a=envelope,
        interpretation='These are paired electrical/current cases for a 31 cm 110-degree tube on a 20 mm nominal neck, a closer geometry class than the earlier 28.6 mm Philips units. They still do not identify the installed AE9VT winding, field profile, or current.'
    )


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['class_cases'])} paired 20 mm-neck catalog cases")
