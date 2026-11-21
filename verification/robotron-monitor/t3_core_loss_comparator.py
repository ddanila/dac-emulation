"""Compare a provisional T3 core shunt with two ferrite data-sheet loss points."""

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PARAMETERS = ROOT / 'reference/k7222-11/t3-coupled-source-ac-loss-parameters.json'
MAGNETICS = ROOT / 'magnetics.py'
FREQUENCY_HZ = 25_000
PEAK_FLUX_T = .2
REFERENCE_TEMPERATURE_C = 100
SINE_FORM_FACTOR = 4.442882938158366
MATERIALS = (
    ('TDK N87', 57_000, 'typical',
     'https://www.tdk-electronics.tdk.com/download/187238/990c299b916e9f3eb7e44ad563b7f0b9/pdf-n87.pdf'),
    ('Ferroxcube 3C90', 80_000, 'maximum',
     'https://www.ferroxcube.com/en-global/download/download/11'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    parameters = json.loads(PARAMETERS.read_text())
    core = parameters['core']
    turns = parameters['groups']['drive'][0]['turns']['value']
    area = core['area_m2']['value']
    length = core['length_m']['value']
    resistance = core['loss_ohm']['value']
    if not all(value > 0 for value in (turns, area, length, resistance)):
        raise ValueError('invalid candidate core geometry or loss shunt')
    if 'Rloss l0 w0n' not in MAGNETICS.read_text():
        raise ValueError('core loss shunt no longer crosses first winding')
    volume = area * length
    sine_voltage_rms = SINE_FORM_FACTOR * FREQUENCY_HZ * turns * area * PEAK_FLUX_T
    shunt_power = sine_voltage_rms**2 / resistance
    comparators = []
    for name, density, qualifier, url in MATERIALS:
        material_power = density * volume
        comparators.append(dict(material=name, source=url, source_loss_kind=qualifier,
                                source_loss_density_w_per_m3=density,
                                candidate_volume_loss_w=material_power,
                                equivalent_first_winding_shunt_ohm=sine_voltage_rms**2/material_power,
                                candidate_shunt_power_divided_by_material_power=shunt_power/material_power))
    return dict(
        format='dac-monitor-t3-core-loss-comparator-v1',
        qualification='reference-condition comparison only; not a .11 material identification, '
                      '16 kHz pulse-loss bound or replacement T3 parameter',
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (PARAMETERS, MAGNETICS, Path(__file__))},
        reference_condition=dict(frequency_hz=FREQUENCY_HZ, peak_sinusoidal_flux_t=PEAK_FLUX_T,
                                 temperature_c=REFERENCE_TEMPERATURE_C,
                                 equation='V_rms = 4.442882938 f N A B_peak; P = V_rms^2 / R'),
        candidate=dict(first_winding_turns=turns, core_area_m2=area,
                       magnetic_path_length_m=length, core_volume_m3=volume,
                       first_winding_sine_voltage_rms_v=sine_voltage_rms,
                       core_loss_shunt_ohm=resistance,
                       equivalent_shunt_power_w=shunt_power),
        comparators=comparators,
        conclusion='The 10 kohm candidate shunt dissipates more than either modern ferrite '
                   'comparator at the same hypothetical 25 kHz/200 mT sine flux. The .11 '
                   'material, core volume, temperature and actual 16 kHz pulse flux are '
                   'unqualified, so this cannot set or bound the operating T3 loss shunt.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('candidate loss', round(report['candidate']['equivalent_shunt_power_w'], 3), 'W')
