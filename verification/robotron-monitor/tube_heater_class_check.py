"""Check the ideal-rail tube heater against a primary same-class catalog page.

Tungsram M31-120 is a 31 cm, 110-degree monitor tube, not an identification of
the installed B31G22. Its printed heater point is used as a class comparator.
"""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import electrothermal
import steady_supply


ROOT = Path(__file__).resolve().parent
SOURCE_SHA256 = '3358775dc8165afc7036235d2887264820017453e13d3d0dd8dd52a40583ac15'
CATALOG_HEATER_V = 11.0
CATALOG_HEATER_A = .068


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run(source_pdf):
    source_pdf = Path(source_pdf)
    if sha(source_pdf.read_bytes()) != SOURCE_SHA256:
        raise ValueError('Tungsram 1976 catalog PDF differs from inspected source')
    with tempfile.TemporaryDirectory() as temporary:
        assembly = steady_supply.assemble(Path(temporary)/'assembly')
    r22 = [row for row in assembly['components']
           if row['source_id'] == '012-6921:R22']
    if (len(r22) != 1 or r22[0]['nodes'] != ['p12', 'p10_7']
            or float(r22[0]['value']) != 15):
        raise ValueError('assembled CRT series heater resistor differs from source')
    supply_v = 12.0
    resistor_ohm = float(r22[0]['value'])
    target_hot_ohm = CATALOG_HEATER_V/CATALOG_HEATER_A
    needed_rail_v = CATALOG_HEATER_V+resistor_ohm*CATALOG_HEATER_A
    equilibrium = steady_supply.heater_equilibrium()
    model = electrothermal.parameters()
    hot_ohm = model['heater_cold_ohm']*(1+model['heater_alpha']*
                                       equilibrium['temperature_rise_k'][0])
    heater_a = supply_v/(resistor_ohm+hot_ohm)
    heater_v = heater_a*hot_ohm
    heater_w = heater_a*heater_v
    if abs(heater_w-equilibrium['heater_power_w']) > 1e-10:
        raise ValueError('active heater branch does not close its heat balance')
    if abs(heater_v/CATALOG_HEATER_V-1) > .02 or abs(heater_a/CATALOG_HEATER_A-1) > .02:
        raise ValueError('active heater point no longer matches the class comparator')
    scenarios = []
    for factor in (.8, 1., 1.2):
        resistance = target_hot_ohm*factor
        current = supply_v/(resistor_ohm+resistance)
        voltage = current*resistance
        scenarios.append(dict(hot_resistance_factor=factor,
                              hot_resistance_ohm=resistance,
                              heater_current_a=current,
                              heater_voltage_v=voltage,
                              heater_power_w=voltage*current))
    return dict(format='dac-monitor-tube-heater-class-check-v1',
                qualification='Tungsram M31-120 manufacturer comparator and active-branch consistency only; installed B31G22 heater, cold resistance, thermal law and emission remain unqualified',
                source=dict(manufacturer='Tungsram', title='Electron Tubes, Semiconductors 1976',
                            url='https://frank.pocnet.net/other/Tungsram/Tungsram_ElectronTubes_Semiconductors_1976.pdf',
                            pdf_sha256=SOURCE_SHA256, pdf_page=96, printed_page='II-46',
                            read_methods=['page image at 180 dpi', 'independent Ghostscript text extraction']),
                comparator=dict(type='M31-120', exact_installed_type=False,
                                heater_voltage_v=CATALOG_HEATER_V,
                                heater_current_a=CATALOG_HEATER_A,
                                deflection_angle_deg=110,
                                useful_area_mm=[257, 195],
                                typical_anode_voltage_v=11000,
                                typical_grid2_voltage_v=250,
                                grid_control_cutoff_v=[35, 69],
                                cathode_control_cutoff_v=[32, 58]),
                assembled_branch=dict(source_id=r22[0]['source_id'],
                                      source_nodes=r22[0]['nodes'],
                                      source_resistance_ohm=resistor_ohm,
                                      ideal_rail_v=supply_v,
                                      model_sha256=sha((ROOT/'electrothermal.py').read_bytes()),
                                      steady_supply_sha256=sha((ROOT/'steady_supply.py').read_bytes()),
                                      cold_resistance_ohm=model['heater_cold_ohm'],
                                      alpha_per_k=model['heater_alpha'],
                                      heater_temperature_rise_k=equilibrium['temperature_rise_k'][0],
                                      cathode_temperature_rise_k=equilibrium['temperature_rise_k'][1],
                                      effective_hot_resistance_ohm=hot_ohm,
                                      heater_current_a=heater_a,
                                      heater_voltage_v=heater_v,
                                      heater_power_w=heater_w),
                comparison=dict(catalog_hot_resistance_ohm=target_hot_ohm,
                                rail_needed_for_exact_catalog_point_v=needed_rail_v,
                                heater_voltage_relative_error=heater_v/CATALOG_HEATER_V-1,
                                heater_current_relative_error=heater_a/CATALOG_HEATER_A-1,
                                hot_resistance_relative_error=hot_ohm/target_hot_ohm-1),
                assumed_class_spread=dict(reason='declared +/-20% effective hot-resistance sensitivity, not a manufacturer limit or B31G22 rating',
                                          scenarios=scenarios),
                remaining=['identify B31G22 manufacturer heater limits directly',
                           'bound cold resistance and temperature coefficient from a compatible source',
                           'bound thermal transfer and emission parameters separately',
                           'check held-warm connected tube load against sustained grid evidence'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('heater comparator relative errors:',
          result['comparison']['heater_voltage_relative_error'],
          result['comparison']['heater_current_relative_error'])
