"""Concentric cosine-sheet yoke: an explicitly assumed reduced magnetic model.

Solve the m=1 magnetostatic boundary problem exactly in four radial regions:
empty bore, winding-to-core air, linear ferrite, exterior air. Inside the bore
B is uniform. The declared axial envelope is included in BOTH flux linkage and
energy (integral g² dz = 3 length/2); this is a separable reduced model, not a
three-dimensional end-field or historical winding reconstruction.
"""
import json
import math
from pathlib import Path

MU0=4*math.pi*1e-7
DEFAULT=Path(__file__).parent/'profiles/k7222-11-yoke-geometry.json'


def solve(matrix,rhs):
    a=[list(row)+[v] for row,v in zip(matrix,rhs)];n=len(a)
    for i in range(n):
        pivot=max(range(i,n),key=lambda j:abs(a[j][i]));a[i],a[pivot]=a[pivot],a[i]
        if abs(a[i][i])<1e-15:raise ValueError('singular magnetic boundary problem')
        scale=a[i][i];a[i]=[v/scale for v in a[i]]
        for j in range(n):
            if j!=i:
                scale=a[j][i];a[j]=[x-scale*y for x,y in zip(a[j],a[i])]
    return [row[-1] for row in a]


def coefficients(b,c,mu):
    # A/(mu0 K a) = u*x + v/x; bore v=0, exterior u=0.
    return solve([[1,-1,-1,0,0,0],[1,-1,1,0,0,0],
        [0,b,1/b,-b,-1/b,0],[0,1,-1/b**2,-1/mu,1/(mu*b*b),0],
        [0,0,0,c,1/c,-1/c],[0,0,0,1/mu,-1/(mu*c*c),1/(c*c)]],
        [0,1,0,0,0,0])


def energy_integral(coef,b,c,mu,steps,outer):
    u0,u1,v1,u2,v2,v3=coef
    value=u0*u0  # exact bore contribution, no singular axis quadrature
    for lo,hi,u,v,permeability in ((1,b,u1,v1,1),(b,c,u2,v2,mu),(c,outer,0,v3,1)):
        h=math.log(hi/lo)/steps
        for i in range(steps):
            x=lo*math.exp((i+.5)*h)
            # Integral ((f/x)^2 + f'^2)*x dx in log-radius coordinates.
            value+=((u+v/x**2)**2+(u-v/x**2)**2)*x*x*h/permeability
    return value


def derive(profile):
    if profile.get('format')!='dac-cosine-sheet-yoke-v1':raise ValueError('unsupported geometric yoke')
    for k in ('neck_radius_m','field_start_m','field_length_m','core_inner_radius_m',
              'core_outer_radius_m','relative_permeability','copper_resistivity_ohm_m','maximum_fill_fraction'):
        if type(profile[k]) not in (int,float) or not math.isfinite(profile[k]) or profile[k]<=0:
            raise ValueError('invalid geometry '+k)
    length=profile['field_length_m'];b=profile['core_inner_radius_m'];c=profile['core_outer_radius_m']
    mu=profile['relative_permeability'];rho=profile['copper_resistivity_ohm_m']
    if not (1<=mu<=10000 and 0<profile['maximum_fill_fraction']<=.7 and b<c<=.1
            and .005<=profile['neck_radius_m']<=.03 and .01<=length<=.1 and 1e-8<=rho<=1e-7):
        raise ValueError('invalid core or winding fill bound')
    electrical={};field=dict(yoke_start_m=profile['field_start_m'],yoke_length_m=length,neck_radius_m=profile['neck_radius_m']);axes={}
    for axis in ('horizontal','vertical'):
        p=profile[axis];a=p['sheet_radius_m'];thickness=p['winding_thickness_m']
        target=p['target_inductance_h'];resistance=p['target_resistance_ohm']
        if not all(type(v) in (int,float) and math.isfinite(v) and v>0 for v in (a,thickness,target,resistance)):
            raise ValueError('invalid winding dimensions or constraints')
        if not profile['neck_radius_m']<a-thickness/2<a+thickness/2<b:
            raise ValueError('winding does not clear neck/core')
        # The lower limits also admit the catalogued 228 uH/0.41 ohm
        # 31 cm, 110-degree AT1039/03 sensitivity comparator.
        if not .0002<=target<=.08 or not .4<=resistance<=40:
            raise ValueError('electrical constraint outside hypothesis bounds')
        coef=coefficients(b/a,c/a,mu);u0=coef[0]
        # K=N I/(2a), N is the total effective turn count on either sheet half.
        per_turn_l=math.pi*MU0/4*u0*1.5*length
        turns=max(1,round(math.sqrt(target/per_turn_l)))
        inductance=per_turn_l*turns*turns
        wire_length=turns*(2*length+2*math.pi*a)
        wire_area=rho*wire_length/resistance
        # Peak cosine current density: N wires / (2a), radial packing window.
        fill=turns*wire_area/(2*a*thickness)
        if fill>profile['maximum_fill_fraction']:raise ValueError('impossible winding fill: '+axis)
        if abs(inductance/target-1)>.01:raise ValueError('integer turns cannot meet inductance constraint')
        checks=[]
        for steps,outer in ((128,64*c/a),(256,64*c/a),(256,128*c/a)):
            integral=energy_integral(coef,b/a,c/a,mu,steps,outer)
            checks.append(math.pi*MU0*turns**2/4*1.5*length*integral)
        error=max(abs(v/inductance-1) for v in checks)
        if error>=.01:raise ValueError('magnetic energy/flux refinement failed')
        electrical[f'yoke_{axis}_l']=inductance;electrical[f'yoke_{axis}_r']=resistance
        field[f'{axis}_tesla_per_amp']=MU0*turns/(2*a)*u0
        axes[axis]=dict(turns=turns,wire_length_m=wire_length,wire_area_m2=wire_area,
            wire_diameter_m=math.sqrt(4*wire_area/math.pi),fill_fraction=fill,
            inductance_flux_h=inductance,inductance_energy_h=checks,
            energy_flux_relative_error=error,dimensionless_radial_coefficients=coef)
    # Orthogonal ideal cosine sheets have zero mutual inductance by symmetry.
    h,v=profile['horizontal'],profile['vertical']
    if abs(h['sheet_radius_m']-v['sheet_radius_m'])< (h['winding_thickness_m']+v['winding_thickness_m'])/2:
        raise ValueError('winding regions overlap')
    return dict(electrical=electrical,field=field,axes=axes,
        qualification='assumed-geometry-reduced-magnetostatic-model',
        inductance_field_relationship_verified=True,specimen_validated=False,
        limitations=['Finite packing regions represented magnetically by ideal thin cosine sheets; linear ferrite; no saturation, hysteresis or frequency-dependent core loss.',
          'Separable axial field/end-return approximation; not a solved 3D fringe field.',
          'Wire resistance uses declared copper resistivity and idealized saddle return length.',
          'Geometry and electrical target constraints are unmeasured hypotheses, not fitted to an image.'])


def read(path=DEFAULT):
    return derive(json.loads(Path(path).read_text()))
