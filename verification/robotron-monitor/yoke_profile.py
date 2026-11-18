"""Shared, explicitly uncalibrated electrical/optical yoke assumptions."""
import json
import math
from pathlib import Path
import trajectory

DEFAULT=Path(__file__).parent/'profiles/k7222-11-yoke.json'


def read(path=DEFAULT):
    p=json.loads(Path(path).read_text())
    if p.get('format')=='dac-cosine-sheet-yoke-v1':
        import yoke_geometry
        result=yoke_geometry.derive(p)
        trajectory.parameters(result['field'])
        return result
    if p.get('format')!='dac-reduced-yoke-v1' or p.get('inductance_field_relationship_verified') is not False:
        raise ValueError('expected explicitly unverified reduced yoke profile')
    electrical={};field={}
    for axis in ('horizontal','vertical'):
        values=p[axis]
        for name,bounds in (('resistance_ohm',(.5,40)),('inductance_h',(.0004,.08)),('tesla_per_amp',(.00012,.012))):
            v=values[name]
            if type(v) not in (int,float) or not math.isfinite(v) or not bounds[0]<=v<=bounds[1]:raise ValueError('invalid yoke '+name)
        electrical[f'yoke_{axis}_r']=values['resistance_ohm']
        electrical[f'yoke_{axis}_l']=values['inductance_h']
        field[f'{axis}_tesla_per_amp']=values['tesla_per_amp']
    field.update(yoke_start_m=p['field_start_m'],yoke_length_m=p['field_length_m'])
    trajectory.parameters(field)
    if p['field_envelope']!='2*sin(pi*z/length)^2':raise ValueError('unsupported yoke field envelope')
    # Diagnostic equivalent volume from L I²/2 = B² V/(2 mu0).
    # This does not assert a geometric volume or fit a winding reconstruction.
    volumes={a:4*math.pi*1e-7*p[a]['inductance_h']/p[a]['tesla_per_amp']**2 for a in ('horizontal','vertical')}
    return dict(electrical=electrical,field=field,effective_energy_volume_m3=volumes,
                qualification=p['qualification'],inductance_field_relationship_verified=False,limitations=p['limitations'])
