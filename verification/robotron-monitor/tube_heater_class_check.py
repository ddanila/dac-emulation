"""Check the heater against a same-class tube and tungsten resistivity.

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
TUNGSTEN_SHA256 = 'acab337e7dcf88cc01ab15a70abab0978a0d2c94c827ffcd709bcfb54c305021'
CATALOG_HEATER_V = 11.0
CATALOG_HEATER_A = .068
TUNGSTEN_RESISTIVITY_MICRO_OHM_M = {300: .053, 1000: .245, 1200: .305, 1400: .366}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def branch_equilibrium(cold_ohm, alpha_per_k, supply_v=12., resistor_ohm=15.):
    """Solve only the heater/R22/thermal DC operating point."""
    overrides = {'heater_cold_ohm': cold_ohm, 'heater_alpha': alpha_per_k}
    low, high = 0., supply_v**2/(4*resistor_ohm)
    for _ in range(80):
        power = (low+high)/2
        heater_rise, _ = electrothermal.steady_temperatures(power, overrides)
        hot_ohm = cold_ohm*(1+alpha_per_k*heater_rise)
        actual = (supply_v/(resistor_ohm+hot_ohm))**2*hot_ohm
        if actual > power:
            low = power
        else:
            high = power
    power = (low+high)/2
    heater_rise, cathode_rise = electrothermal.steady_temperatures(power, overrides)
    hot_ohm = cold_ohm*(1+alpha_per_k*heater_rise)
    current = supply_v/(resistor_ohm+hot_ohm)
    voltage = current*hot_ohm
    if abs(voltage*current-power) > 1e-10:
        raise ValueError('heater corner does not close heat balance')
    return dict(cold_resistance_ohm=cold_ohm, alpha_per_k=alpha_per_k,
                heater_temperature_rise_k=heater_rise,
                cathode_temperature_rise_k=cathode_rise,
                effective_hot_resistance_ohm=hot_ohm,
                heater_current_a=current, heater_voltage_v=voltage,
                heater_power_w=power)


def run(source_pdf, tungsten_pdf):
    source_pdf = Path(source_pdf)
    if sha(source_pdf.read_bytes()) != SOURCE_SHA256:
        raise ValueError('Tungsram 1976 catalog PDF differs from inspected source')
    if sha(Path(tungsten_pdf).read_bytes()) != TUNGSTEN_SHA256:
        raise ValueError('NASA tungsten handbook PDF differs from inspected source')
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
    rho = TUNGSTEN_RESISTIVITY_MICRO_OHM_M
    ratios = {temperature: rho[temperature]/rho[300]
              for temperature in (1000, 1200, 1400)}
    linear_slopes = {temperature: (ratio-1)/(temperature-300)
                     for temperature, ratio in ratios.items()}
    cold_from_catalog = {temperature: target_hot_ohm/ratio
                         for temperature, ratio in ratios.items()}
    if not (electrothermal.BOUNDS['heater_cold_ohm'][1] <= model['heater_cold_ohm']
            <= electrothermal.BOUNDS['heater_cold_ohm'][2]
            and electrothermal.BOUNDS['heater_alpha'][1] <= model['heater_alpha']
            <= electrothermal.BOUNDS['heater_alpha'][2]
            and min(linear_slopes.values()) <= model['heater_alpha'] <= max(linear_slopes.values())
            and min(cold_from_catalog.values()) <= model['heater_cold_ohm'] <= max(cold_from_catalog.values())):
        raise ValueError('active heater proxy misses tungsten/tube class comparison')
    corners = [branch_equilibrium(cold, alpha)
               for cold in electrothermal.BOUNDS['heater_cold_ohm'][1:3]
               for alpha in electrothermal.BOUNDS['heater_alpha'][1:3]]
    nominal_branch = branch_equilibrium(model['heater_cold_ohm'], model['heater_alpha'])
    if abs(nominal_branch['heater_current_a']-heater_a) > 1e-12:
        raise ValueError('independent nominal heater solve differs from assembly')
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
    return dict(format='dac-monitor-tube-heater-class-check-v2',
                qualification='M31-120 hot-point and pure-tungsten resistance class proxy; installed B31G22 heater material, temperature, limits and emission remain unqualified',
                source=dict(manufacturer='Tungsram', title='Electron Tubes, Semiconductors 1976',
                            url='https://frank.pocnet.net/other/Tungsram/Tungsram_ElectronTubes_Semiconductors_1976.pdf',
                            pdf_sha256=SOURCE_SHA256, pdf_page=96, printed_page='II-46',
                            read_methods=['page image at 180 dpi', 'independent Ghostscript text extraction']),
                tungsten_source=dict(authority='NASA', title='Space Nuclear Propulsion Material Property Handbook',
                                     url='https://ntrs.nasa.gov/api/citations/20240004217/downloads/SNP-HDBK-0008_SNP-Material-Handbook.pdf',
                                     pdf_sha256=TUNGSTEN_SHA256,
                                     section='3.2.1 Tungsten (W), electrical resistivity with temperature',
                                     printed_page=148,
                                     resistivity_micro_ohm_m={str(k): v for k, v in rho.items()},
                                     interpretation='pure tungsten material comparator, not a B31G22 heater identification'),
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
                cold_resistance_proxy=dict(
                    equation='R_hot/R_300 = rho(T_hot)/rho(300 K); alpha_linear = (R_hot/R_300 - 1)/(T_hot - 300 K)',
                    ratios_to_300k={str(k): v for k, v in ratios.items()},
                    implied_linear_alpha_per_k={str(k): v for k, v in linear_slopes.items()},
                    cold_ohm_from_catalog_hot_point={str(k): v for k, v in cold_from_catalog.items()},
                    active_cold_bounds_ohm=list(electrothermal.BOUNDS['heater_cold_ohm'][1:3]),
                    active_alpha_bounds_per_k=list(electrothermal.BOUNDS['heater_alpha'][1:3]),
                    nominal_branch=nominal_branch, joint_bound_corners=corners,
                    limitation='The 300 K material reference approximates the model 293 K ambient. The thermal heater temperature and pure-tungsten composition are class assumptions; independent rectangular parameter corners need not match the catalog hot point.'),
                assumed_class_spread=dict(reason='declared +/-20% effective hot-resistance sensitivity, not a manufacturer limit or B31G22 rating',
                                          scenarios=scenarios),
                remaining=['identify B31G22 manufacturer heater material and limits directly',
                           'bound thermal transfer and emission parameters separately',
                           'check held-warm connected tube load against sustained grid evidence'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--tungsten-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf, args.tungsten_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('heater comparator relative errors:',
          result['comparison']['heater_voltage_relative_error'],
          result['comparison']['heater_current_relative_error'])
