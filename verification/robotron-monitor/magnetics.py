"""Shared-core XSPICE transformer construction; no historical winding claims.

Uses ngspice 45 manual §§8.2.21–22 lcouple/core. Every winding participates
in one magnetic loop; a shorted turn is a separate closed electrical winding.
Monotone, odd B(H) tables give reversible saturation. A primary shunt models
aggregate core loss; hysteresis and distributed winding resonances are excluded.
"""
import math
import re

EQUIVALENT_COUPLING = 0.999


def winding_network(i,w,a,z):
    """Optional passive one-pole AC copper-loss approximation.

    R || L adds frequency-dependent resistance while preserving declared DC R
    and low-frequency total leakage. It never adds a damping power source.
    The AC resistance and leakage fraction require explicit caller provenance.
    """
    lines=[f'Rw{i} {a} r{i} {w["resistance_ohm"]:.15g}']
    node=f'r{i}';leak=w['leakage_h']
    if 'skin_resistance_ohm' in w:
        fraction=w['skin_fraction'];node=f'skin{i}'
        lines += [f'Rskin{i} r{i} {node} {w["skin_resistance_ohm"]:.15g}',
                  f'Lskin{i} r{i} {node} {leak*fraction:.15g}']
        leak*=1-fraction
    lines += [f'Ll{i} {node} l{i} {leak:.15g}',
              f'Cw{i} {a} {z} {w["capacitance_f"]:.15g}']
    return lines


def transformer_flux(name, windings, core, shorted_turns=None, *, smoothing_t=1e-5):
    """Shared B-state equivalent of the reversible core, using native devices.

    Faraday's law integrates winding voltage; Ampere's law sets magnetizing
    current. Secondary source currents reflect into the primary, conserving
    terminal power. No prescribed switching waveform or independent power rail.
    The odd piecewise-linear inverse B(H) is smoothed over 10 uT at its knees.
    This backend avoids XSPICE core state in stiff switched networks.
    """
    transformer(name, windings, core, shorted_turns)  # same physical validation
    if not math.isfinite(smoothing_t) or not 0 < smoothing_t <= 1e-3:
        raise ValueError('invalid B(H) knee regularization')
    ws = list(windings)
    if shorted_turns:
        ws.append(dict(turns=shorted_turns['turns'], resistance_ohm=shorted_turns['resistance_ohm'],
                       leakage_h=shorted_turns['leakage_h'], capacitance_f=1e-15, polarity=1))
    ports=[]; lines=[]
    for i,w in enumerate(ws):
        a,z=(f'w{i}p',f'w{i}n') if i<len(windings) else ('shorted','shorted')
        if i<len(windings): ports += [a,z]
        lines += winding_network(i,w,a,z)
    n0=ws[0]['turns']; sign0=ws[0].get('polarity',1)
    h=core['h_a_per_m']; b=core['b_t']; center=h.index(0)
    h=h[center:]; b=b[center:]
    slopes=[(y-x)/(by-bx) for x,y,bx,by in zip(h,h[1:],b,b[1:])]
    expression=f'{slopes[0]:.15g}*v(flux_b)'
    for i in range(1,len(slopes)):
        knee=b[i]; delta=slopes[i]-slopes[i-1]
        expression += (f'+({delta:.15g})*(v(flux_b)+.5*'
                       f'(sqrt((v(flux_b)-{knee:.15g})^2+{smoothing_t**2:.15g})'
                       f'-sqrt((v(flux_b)+{knee:.15g})^2+{smoothing_t**2:.15g})))')
    current=f'({sign0*core["length_m"]/n0:.15g})*({expression})'
    for i,w in enumerate(ws[1:],1):
        z=f'w{i}n' if i<len(windings) else 'shorted'
        ratio=sign0*w.get('polarity',1)*w['turns']/n0
        lines.append(f'Ew{i} l{i} {z} l0 w0n {ratio:.15g}')
        # Native CCCS stamps current reflection directly into the matrix. A
        # behavioral i(Ew) feedback loop can force tiny steps in switching loads.
        lines.append(f'Fw{i} l0 w0n Ew{i} {-ratio:.15g}')
    lines += ['Cflux flux_b 0 1 IC=0', 'Rflux flux_b 0 1e12',
              f'Bflux 0 flux_b I={{{sign0/(n0*core["area_m2"]):.15g}*v(l0,w0n)}}',
              f'Bprimary l0 w0n I={{{current}}}',
              f'Rloss l0 w0n {core["loss_ohm"]:.15g}']
    if shorted_turns: lines.append('Rshortref shorted 0 1e12')
    return '\n'.join([f'.subckt {name} '+' '.join(ports),*lines,'.ends '+name])+'\n'


def transformer_coupled(name, windings, core, shorted_turns=None, *,
                        high_voltage_index=None, high_voltage_coupling=None):
    """Passive linear multi-winding equivalent with explicit shared coupling.

    A selected HV-overwind coupling replaces the provisional 0.999 value
    only on pairs containing that section. Mutual leakage adds to each
    declared section's provisional series leakage.
    """
    transformer(name, windings, core, shorted_turns)
    if (high_voltage_index is None) != (high_voltage_coupling is None):
        raise ValueError('HV coupling needs both winding index and coefficient')
    if high_voltage_index is not None and (
            type(high_voltage_index) is not int or
            not 0 < high_voltage_index < len(windings) or
            not math.isfinite(high_voltage_coupling) or
            not 0 < high_voltage_coupling < EQUIVALENT_COUPLING):
        raise ValueError('invalid HV overwind coupling')
    ws = list(windings)
    if shorted_turns:
        ws.append(dict(turns=shorted_turns['turns'],
                       resistance_ohm=shorted_turns['resistance_ohm'],
                       leakage_h=shorted_turns['leakage_h'],
                       capacitance_f=1e-15, polarity=1))
    ports = []
    lines = []
    magnetizing_inductances = []
    center = core['h_a_per_m'].index(0)
    mu = ((core['b_t'][center+1]-core['b_t'][center]) /
          (core['h_a_per_m'][center+1]-core['h_a_per_m'][center]))
    for i, winding in enumerate(ws):
        a, z = (f'w{i}p', f'w{i}n') if i < len(windings) else ('shorted', 'shorted')
        if i < len(windings):
            ports += [a, z]
        lines += winding_network(i, winding, a, z)
        inductance = winding['turns']**2*core['area_m2']*mu/core['length_m']
        magnetizing_inductances.append(inductance)
        first, last = ((f'l{i}', z) if winding.get('polarity', 1) == 1
                       else (z, f'l{i}'))
        lines.append(f'Lmag{i} {first} {last} {inductance:.15g}')
    for i in range(len(ws)):
        for j in range(i+1, len(ws)):
            coupling = (high_voltage_coupling if high_voltage_index in (i, j)
                        else EQUIVALENT_COUPLING)
            lines.append(f'Kcore{i}_{j} Lmag{i} Lmag{j} {coupling:.15g}')
    flux_terms = [f'{magnetizing_inductances[0]:.15g}*i(Lmag0)']
    flux_terms += [f'{(high_voltage_coupling if i == high_voltage_index else EQUIVALENT_COUPLING)*math.sqrt(magnetizing_inductances[0]*inductance):.15g}*i(Lmag{i})'
                   for i, inductance in enumerate(magnetizing_inductances[1:], 1)]
    lines += [f'Rloss l0 w0n {core["loss_ohm"]:.15g}',
              f'Bflux flux_b 0 V={{({"+".join(flux_terms)})/{ws[0]["turns"]*core["area_m2"]:.15g}}}']
    if shorted_turns:
        lines.append('Rshortref shorted 0 1e12')
    return '\n'.join([f'.subckt {name} '+' '.join(ports), *lines,
                      '.ends '+name])+'\n'


def transformer(name,windings,core,shorted_turns=None):
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name):raise ValueError('invalid transformer name')
    if not 2<=len(windings)<=63:raise ValueError('transformer needs 2–63 winding sections')
    for key in ('area_m2','length_m','loss_ohm'):
        if not math.isfinite(core[key]) or core[key]<=0:raise ValueError('invalid core parameter')
    h,b=core['h_a_per_m'],core['b_t']
    if (len(h)!=len(b) or len(h)<3 or any(not math.isfinite(v) for v in h+b)
        or any(y<=x for x,y in zip(h,h[1:])) or any(y<=x for x,y in zip(b,b[1:]))
        or 0 not in h or b[h.index(0)]!=0
        or any(abs(x+y)>1e-10 for x,y in zip(h,reversed(h)))
        or any(abs(x+y)>1e-10 for x,y in zip(b,reversed(b)))):
        raise ValueError('core B(H) must be finite, strictly monotone, odd and pass through zero')
    ports=[];lines=[];all_windings=list(windings)
    if shorted_turns:
        all_windings.append(dict(turns=shorted_turns['turns'],resistance_ohm=shorted_turns['resistance_ohm'],
                                 leakage_h=shorted_turns['leakage_h'],capacitance_f=1e-15,polarity=1))
    for i,w in enumerate(all_windings):
        for key in ('turns','resistance_ohm','leakage_h','capacitance_f'):
            if not math.isfinite(w[key]) or w[key]<=0:raise ValueError('invalid winding parameter: '+key)
        if w.get('polarity',1) not in (-1,1):raise ValueError('winding polarity must be +1 or -1')
        skin={'skin_resistance_ohm','skin_fraction'} & w.keys()
        if skin and (len(skin)!=2 or not math.isfinite(w['skin_resistance_ohm'])
                     or w['skin_resistance_ohm']<=0 or not math.isfinite(w['skin_fraction'])
                     or not 0<w['skin_fraction']<1):
            raise ValueError('invalid passive winding AC loss')
        a,z=(f'w{i}p',f'w{i}n') if i<len(windings) else ('shorted','shorted')
        if i<len(windings):ports += [a,z]
        # Explicit resistance, leakage and terminal capacitance for every winding.
        lines += winding_network(i,w,a,z)
        electrical=f'l{i} {z}' if w.get('polarity',1)==1 else f'{z} l{i}'
        lines += [f'Aw{i} ({electrical}) (m{i} m{i+1}) winding{i}',
                  f'.model winding{i} lcouple(num_turns={w["turns"]:.15g})']
    lines += [f'Acore (m{len(all_windings)} m0) magnetic',
              '.model magnetic core(mode=1 H_array=['+' '.join(map(str,h))+']',
              '+ B_array=['+' '.join(map(str,b))+']',
              f'+ area={core["area_m2"]} length={core["length_m"]} input_domain=0.001)',
              'Rmagref m0 0 1e12',f'Rloss l0 w0n {core["loss_ohm"]}']
    if shorted_turns:lines.append('Rshortref shorted 0 1e12')
    return '\n'.join([f'.subckt {name} '+ ' '.join(ports),*lines,'.ends '+name])+'\n'
