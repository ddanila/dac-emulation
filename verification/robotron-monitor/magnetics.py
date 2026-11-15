"""Shared-core XSPICE transformer construction; no historical winding claims.

Uses ngspice 45 manual §§8.2.21–22 lcouple/core. Every winding participates
in one magnetic loop; a shorted turn is a separate closed electrical winding.
Monotone, odd B(H) tables give reversible saturation. A primary shunt models
aggregate core loss; hysteresis and distributed winding resonances are excluded.
"""
import math
import re


def transformer(name,windings,core,shorted_turns=None):
    if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*',name):raise ValueError('invalid transformer name')
    if not 2<=len(windings)<=12:raise ValueError('transformer needs 2–12 windings')
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
        a,z=(f'w{i}p',f'w{i}n') if i<len(windings) else ('shorted','shorted')
        if i<len(windings):ports += [a,z]
        # Explicit resistance, leakage and terminal capacitance for every winding.
        lines += [f'Rw{i} {a} r{i} {w["resistance_ohm"]:.15g}',
                  f'Ll{i} r{i} l{i} {w["leakage_h"]:.15g}',
                  f'Cw{i} {a} {z} {w["capacitance_f"]:.15g}']
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
