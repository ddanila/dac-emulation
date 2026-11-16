"""Electrothermal CRT load for coupled electrical solves; no specimen calibration.

Voltages at th/tc represent temperature rise in kelvin; currents are watts.
Thermal capacitors store sensible heat. Electrical beam current returns to the
cathode, rather than disappearing into ground. All free values are bounded
engineering assumptions until independent tube/heater evidence is available.
"""
import math

# nominal, minimum, maximum, SI unit
BOUNDS = {
    'ambient_k': (293.15,273.15,313.15,'K'),
    'heater_cold_ohm': (20.,5.,60.,'ohm'),
    'heater_alpha': (.008,.002,.015,'1/K'),
    'heater_capacity': (.02,.002,.2,'J/K'),
    'cathode_capacity': (.05,.005,.5,'J/K'),
    'heater_cathode_g': (.002,.0002,.02,'W/K'),
    'heater_ambient_g': (.0002,.00002,.002,'W/K'),
    'cathode_ambient_g': (.0006,.00006,.006,'W/K'),
    'heater_radiation_area': (1e-6,1e-7,1e-5,'m2'),
    'cathode_radiation_area': (1e-6,1e-7,1e-5,'m2'),
    'emission_reference_k': (1000.,800.,1200.,'K'),
    'emission_reference_a': (60e-6,5e-6,300e-6,'A'),
    'work_function_ev': (1.1,.8,1.5,'eV'),
    'perveance': (1e-6,1e-7,1e-5,'A/V^1.5'),
    'grid2_mu': (10.,5.,30.,'1'),
    'grid2_capture': (.03,.005,.15,'1'),
    'anode_collection_v': (1000.,500.,2000.,'V'),
    'cathode_socket_f': (20e-12,5e-12,60e-12,'F'),
}


def parameters(overrides=None):
    values={key: bounds[0] for key,bounds in BOUNDS.items()}
    for key,value in (overrides or {}).items():
        if (key not in BOUNDS or type(value) not in (int,float) or not math.isfinite(value)
                or not BOUNDS[key][1]<=value<=BOUNDS[key][2]):
            raise ValueError('outside electrothermal parameter bounds: '+key)
        values[key]=value
    return values


def model(overrides=None):
    p=parameters(overrides)
    a=p['ambient_k']
    # Emission is referenced at a declared temperature, not a fitted ramp.
    temperature=f'max(v(tc)+{a},1)'
    emission=(f'{p["emission_reference_a"]}*({temperature}/{p["emission_reference_k"]})^2'
              f'*exp(min(60,{p["work_function_ev"]}/8.617333262e-5*'
              f'(1/{p["emission_reference_k"]}-1/({temperature}))))')
    demand=f'{p["perveance"]}*max(v(g1,cathode)+v(g2,cathode)/{p["grid2_mu"]},0)^1.5'
    collected=f'min(max(v(anode,cathode)/{p["anode_collection_v"]},0),1)'
    current=f'min({emission},{demand})'
    r=f'{p["heater_cold_ohm"]}*max(1+{p["heater_alpha"]}*v(th),.1)'
    return f'''* Uncalibrated coupled CRT load; th/tc are temperature rise, not exposed electrical nodes.
.subckt CRT_THERMAL heater_p heater_n cathode g1 g2 anode th tc
Vheater heater_p heater_i 0
Bheater heater_i heater_n I={{v(heater_i,heater_n)/({r})}}
Bheat 0 th I={{v(heater_i,heater_n)^2/({r})}}
Ch th 0 {p['heater_capacity']} IC=0
Cc tc 0 {p['cathode_capacity']} IC=0
Rhc th tc {1/p['heater_cathode_g']}
Rha th 0 {1/p['heater_ambient_g']}
Rca tc 0 {1/p['cathode_ambient_g']}
Bhrad th 0 I={{5.670374419e-8*{p['heater_radiation_area']}*((v(th)+{a})^4-{a}^4)}}
Bcrad tc 0 I={{5.670374419e-8*{p['cathode_radiation_area']}*((v(tc)+{a})^4-{a}^4)}}
Bbeam anode cathode I={{{current}*{collected}*(1-{p['grid2_capture']})}}
Bg2 g2 cathode I={{{current}*{p['grid2_capture']}*min(max(v(g2,cathode),0),1)}}
Csocket cathode 0 {p['cathode_socket_f']}
.ends CRT_THERMAL
'''


def thermal_energy(heater_rise_k,cathode_rise_k,overrides=None):
    p=parameters(overrides)
    if any(not math.isfinite(t) or t<0 for t in (heater_rise_k,cathode_rise_k)):
        raise ValueError('invalid temperature rise')
    return p['heater_capacity']*heater_rise_k+p['cathode_capacity']*cathode_rise_k
