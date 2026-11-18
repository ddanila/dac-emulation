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


def model(overrides=None, *, initial_rise_k=(0., 0.), hold_temperature=False, collection_report=None):
    p=parameters(overrides)
    h0,c0=initial_rise_k
    if any(not math.isfinite(t) or not 0<=t<=10000 for t in (h0,c0)):
        raise ValueError('invalid initial temperature rise')
    if type(hold_temperature) is not bool:raise ValueError('invalid thermal hold mode')
    initialization=(f'Vholdh th 0 {h0}\nVholdc tc 0 {c0}' if hold_temperature else
                    f'.ic v(th)={h0} v(tc)={c0}')
    a=p['ambient_k']
    # Emission is referenced at a declared temperature, not a fitted ramp.
    temperature=f'max(v(tc)+{a},1)'
    emission=(f'{p["emission_reference_a"]}*({temperature}/{p["emission_reference_k"]})^2'
              f'*exp(min(60,{p["work_function_ev"]}/8.617333262e-5*'
              f'(1/{p["emission_reference_k"]}-1/({temperature}))))')
    demand=f'{p["perveance"]}*max(v(g1,cathode)+v(g2,cathode)/{p["grid2_mu"]},0)^1.5'
    collected=f'min(max(v(anode,cathode)/{p["anode_collection_v"]},0),1)'
    current=f'min({emission},{demand})'
    launch=f'{current}*{collected}*(1-{p["grid2_capture"]})'
    grid=f'{current}*{p["grid2_capture"]}*min(max(v(g2,cathode),0),1)'
    collection_source=''
    anode_current='v(launch_current_ua)*1e-6'
    beam_return='cathode'
    if collection_report is not None:
        import collection
        collection_source='Vcollection collection_current_ua 0 '+collection.pwl(collection_report,scale=1e6)
        # Separate emission and arrival terminal currents. Their difference is
        # in-flight charge, accounted by the periodic collection ledger; there
        # is no invented physical capacitance or delayed cathode emission.
        collection_source+='\nBlaunchload 0 cathode I={v(launch_current_ua)*1e-6}'
        beam_return='0'
        anode_current='v(collection_current_ua)*1e-6'
    r=f'{p["heater_cold_ohm"]}*max(1+{p["heater_alpha"]}*v(th),.1)'
    return f'''* Uncalibrated coupled CRT load; th/tc are temperature rise, not exposed electrical nodes.
.subckt CRT_THERMAL heater_p heater_n cathode g1 g2 anode th tc
Vheater heater_p heater_i 0
Bheater heater_i heater_n I={{v(heater_i,heater_n)/({r})}}
Bheat 0 th I={{v(heater_i,heater_n)^2/({r})}}
Ch th 0 {p['heater_capacity']} IC={h0}
Cc tc 0 {p['cathode_capacity']} IC={c0}
{initialization}
Rhc th tc {1/p['heater_cathode_g']}
Rha th 0 {1/p['heater_ambient_g']}
Rca tc 0 {1/p['cathode_ambient_g']}
Bhrad th 0 I={{5.670374419e-8*{p['heater_radiation_area']}*((v(th)+{a})^4-{a}^4)}}
Bcrad tc 0 I={{5.670374419e-8*{p['cathode_radiation_area']}*((v(tc)+{a})^4-{a}^4)}}
* Diagnostic voltages use 1 V/uA to resolve emission above voltage tolerance.
* They are not physical energy-storage nodes.
Blaunch launch_current_ua 0 V={{1e6*({launch})}}
Bemitted emitted_current_ua 0 V={{v(launch_current_ua)+1e6*({grid})}}
{collection_source}
Bbeam anode {beam_return} I={{{anode_current}}}
Bg2 g2 cathode I={{{grid}}}
Csocket cathode 0 {p['cathode_socket_f']}
.ends CRT_THERMAL
'''


def thermal_energy(heater_rise_k,cathode_rise_k,overrides=None):
    p=parameters(overrides)
    if any(not math.isfinite(t) or t<0 for t in (heater_rise_k,cathode_rise_k)):
        raise ValueError('invalid temperature rise')
    return p['heater_capacity']*heater_rise_k+p['cathode_capacity']*cathode_rise_k


def heat_losses(heater_rise_k, cathode_rise_k, overrides=None):
    """Net outward thermal powers at the two nodes, in watts."""
    p=parameters(overrides)
    h,c=heater_rise_k,cathode_rise_k
    thermal_energy(h,c,p)
    a=p['ambient_k'];sigma=5.670374419e-8
    transfer=p['heater_cathode_g']*(h-c)
    return (transfer+p['heater_ambient_g']*h+sigma*p['heater_radiation_area']*((h+a)**4-a**4),
            -transfer+p['cathode_ambient_g']*c+sigma*p['cathode_radiation_area']*((c+a)**4-a**4))


def steady_temperatures(heater_power_w, overrides=None):
    """Unique passive-network equilibrium for an externally averaged heater power.

    Temperatures are rises, not elapsed warm-up time. The 10000 K rise ceiling is
    a numerical validity guard, not a tube rating or a measured operating point.
    """
    p=parameters(overrides)
    if not math.isfinite(heater_power_w) or heater_power_w<0:
        raise ValueError('invalid heater power')
    def heater(c):
        return c+heat_losses(c,c,p)[1]/p['heater_cathode_g']
    lo,hi=0.,10000.
    for _ in range(80):
        c=(lo+hi)/2;h=heater(c)
        if h>10000 or heat_losses(h,c,p)[0]>heater_power_w:hi=c
        else:lo=c
    c=(lo+hi)/2;h=heater(c)
    if abs(heat_losses(h,c,p)[0]-heater_power_w)>max(1e-12,heater_power_w*1e-10):
        raise ValueError('thermal equilibrium outside validity guard')
    return h,c


def equilibrate(electrical_trial, overrides=None, *, max_iterations=64):
    """Couple held-temperature, settled electrical trials to steady heat balance.

    Callback receives (heater rise K, cathode rise K) and must return
    {settled: True, heater_power_w: float, metrics: {name: positive magnitude}}.
    Every callback must solve the circuit; this function cannot qualify a trace
    or provide electrical state continuation. Final replay must release the
    returned temperatures and settle its own uninterrupted electrical run.
    """
    p=parameters(overrides)
    if type(max_iterations) is not int or not 2<=max_iterations<=256:
        raise ValueError('invalid equilibrium iteration budget')
    temperatures=(0.,0.);previous=None;history=[]
    for _ in range(max_iterations):
        trial=electrical_trial(temperatures)
        if trial.get('settled') is not True:raise ValueError('electrical trial did not settle')
        power=trial['heater_power_w'];target=steady_temperatures(power,p)
        metrics=trial['metrics']
        if not metrics or any(not isinstance(k,str) or not math.isfinite(v) or v<=0 for k,v in metrics.items()):
            raise ValueError('invalid equilibrium electrical metrics')
        if previous is not None and set(metrics)!=set(previous):raise ValueError('equilibrium metrics changed')
        delta=max(abs(x-y)/max(p['ambient_k']+x,p['ambient_k']+y) for x,y in zip(temperatures,target))
        losses=heat_losses(*temperatures,p)
        residual=max(abs(losses[0]-power),abs(losses[1]))/max(power,1e-12)
        electrical_delta=(max(abs(v-previous[k])/max(v,previous[k]) for k,v in metrics.items())
                          if previous is not None else None)
        history.append(dict(temperature_rise_k=list(temperatures),heater_power_w=power,
                            thermal_residual=residual,temperature_delta=delta,
                            electrical_delta=electrical_delta,metrics=dict(metrics)))
        if electrical_delta is not None and delta<.01 and residual<.001 and electrical_delta<.01:
            return dict(format='dac-crt-equilibrium-v1',status='converged',
                        temperature_rise_k=list(temperatures),iterations=history,
                        initialization='thermal-equilibrium',elapsed_warmup_s=None,
                        full_monitor_qualified=False)
        temperatures=tuple((x+y)/2 for x,y in zip(temperatures,target))
        previous=dict(metrics)
    raise ValueError('electrothermal equilibrium did not converge')
