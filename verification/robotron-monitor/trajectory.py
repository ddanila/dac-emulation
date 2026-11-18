"""Quasi-static relativistic electron trajectories in parameterized CRT fields.

This is a reduced field model, not a B31G22 field reconstruction. The axial
potential is interpolated between gun electrodes. Its second-order radial
extension satisfies Laplace's equation on axis. The finite yoke field has a
smooth envelope; fringe-field geometry, space charge and aberrations beyond
the near-axis potential expansion remain unmodeled. No tube calibration implied.

Independent variable is axial position, SI units. Fourth-order Runge-Kutta
integrates position, normalized momentum p/(m*c), and flight time. Backward
electrons and aperture/screen misses are explicitly reported, not recentered.
"""
import math
import collection

from optics import ELECTRON_CHARGE as E, ELECTRON_MASS as M

C = 299792458.
REST_EV = M*C*C/E
DEFAULTS = dict(screen_z_m=.28, screen_radius_m=.45, screen_width_m=.210,
                screen_height_m=.145, gun_radius_m=.002, neck_radius_m=.010,
                yoke_start_m=.075, yoke_length_m=.040,
                horizontal_tesla_per_amp=.0012, vertical_tesla_per_amp=.0012,
                initial_energy_ev=20., source_radius_m=5e-6, divergence_rad=.001,
                grid2_length_m=.012, focus_start_m=.015, focus_length_m=.015,
                anode_start_m=.040, anode_length_m=.030)


def smooth(z, begin, length):
    """Quintic transition with its first three spatial derivatives."""
    s=(z-begin)/length
    if s<=0: return (0.,0.,0.,0.)
    if s>=1: return (1.,0.,0.,0.)
    return (6*s**5-15*s**4+10*s**3,
            (30*s**4-60*s**3+30*s*s)/length,
            (120*s**3-180*s*s+60*s)/length**2,
            (360*s*s-360*s+60)/length**3)


def potential(x,y,z,anode,grid2,focus,p=None):
    p=DEFAULTS if p is None else p
    values=[0.,0.,0.,0.]
    # Electrode distances are declared assumptions, not tube drawing dimensions.
    for amplitude,begin,length in ((grid2,0.,p['grid2_length_m']),
                                   (focus-grid2,p['focus_start_m'],p['focus_length_m']),
                                   (anode-focus,p['anode_start_m'],p['anode_length_m'])):
        for i,v in enumerate(smooth(z,begin,length)): values[i]+=amplitude*v
    phi,d1,d2,d3=values
    r2=x*x+y*y
    return phi-r2*d2/4, (-x*d2/2,-y*d2/2,d1-r2*d3/4)


def parameters(overrides=None):
    p=DEFAULTS | (overrides or {})
    if set(p)!=set(DEFAULTS) or any(not math.isfinite(v) or v<=0 for v in p.values()):
        raise ValueError('unknown, nonfinite or nonpositive field parameter')
    if not (p['grid2_length_m']<=p['focus_start_m'] and
            p['focus_start_m']+p['focus_length_m']<=p['anode_start_m'] and
            p['anode_start_m']+p['anode_length_m']<=p['yoke_start_m']<
            p['yoke_start_m']+p['yoke_length_m']<p['screen_z_m']):
        raise ValueError('invalid gun/yoke/screen ordering')
    if math.hypot(p['screen_width_m']/2,p['screen_height_m']/2)>=p['screen_radius_m']:
        raise ValueError('screen is outside curvature radius')
    return p


def ray(anode,grid2,focus,ih,iv,*,origin=(0.,0.),slope=(0.,0.),step_m=.0002,overrides=None):
    p=parameters(overrides)
    if not all(math.isfinite(v) for v in (anode,grid2,focus,ih,iv,*origin,*slope)) or not 1e-6<=step_m<=.001:
        raise ValueError('invalid ray inputs or step')
    result=dict(landed=False,reason='low acceleration',points=[],flight_s=0.,energy_error_ev=0.,impact_energy_ev=0.)
    if anode<=100: return collection.annotate(result)
    gamma=1+p['initial_energy_ev']/REST_EV
    u=math.sqrt((gamma-1)*(gamma+1))
    uz=u/math.sqrt(1+slope[0]**2+slope[1]**2)
    state=[origin[0],origin[1],slope[0]*uz,slope[1]*uz,uz,0.]
    initial_phi=potential(*origin,0,anode,grid2,focus,p)[0]
    energy0=p['initial_energy_ev']-initial_phi

    def rhs(z,s):
        x,y,ux,uy,uz,_=s
        if uz<=1e-9: raise ArithmeticError('electron reversed')
        gamma=math.sqrt(1+ux*ux+uy*uy+uz*uz)
        _,gradient=potential(x,y,z,anode,grid2,focus,p)
        q=(z-p['yoke_start_m'])/p['yoke_length_m']
        envelope=2*math.sin(math.pi*q)**2 if 0<q<1 else 0.
        bx=-iv*p['vertical_tesla_per_amp']*envelope
        by=ih*p['horizontal_tesla_per_amp']*envelope
        electric=E/(M*C*C)*gamma/uz
        magnetic=E/(M*C)/uz
        return [ux/uz,uy/uz,electric*gradient[0]+magnetic*uz*by,
                electric*gradient[1]-magnetic*uz*bx,
                electric*gradient[2]-magnetic*(ux*by-uy*bx),gamma/(C*uz)]

    def surface(s):
        radial=s[0]**2+s[1]**2
        if radial>=p['screen_radius_m']**2: return -math.inf
        return p['screen_z_m']-p['screen_radius_m']+math.sqrt(p['screen_radius_m']**2-radial)

    z=0.
    points=[[z,state[0],state[1]]]
    max_error=0.
    gun_end=p['anode_start_m']+p['anode_length_m']
    neck_end=p['yoke_start_m']+p['yoke_length_m']
    boundaries=sorted({p['grid2_length_m'],p['focus_start_m'],
        p['focus_start_m']+p['focus_length_m'],p['anode_start_m'],
        gun_end,p['yoke_start_m'],neck_end,p['screen_z_m']})
    for index in range(math.ceil(p['screen_z_m']/step_m)+len(boundaries)+2):
        old=state; previous_z=z
        end=min(z+step_m,next(b for b in boundaries if b>z))
        h=end-z
        try:
            a=rhs(z,old)
            b=rhs(z+h/2,[s+h*v/2 for s,v in zip(old,a)])
            c=rhs(z+h/2,[s+h*v/2 for s,v in zip(old,b)])
            d=rhs(z+h,[s+h*v for s,v in zip(old,c)])
        except ArithmeticError:
            result['reason']='electron reversed'; break
        state=[s+h*(v+2*w+2*t+r)/6 for s,v,w,t,r in zip(old,a,b,c,d)]
        z=end
        if not all(math.isfinite(v) for v in state):
            raise ValueError('nonfinite trajectory')
        k=REST_EV*(math.sqrt(1+sum(v*v for v in state[2:5]))-1)
        phi=potential(state[0],state[1],z,anode,grid2,focus,p)[0]
        max_error=max(max_error,abs(k-phi-energy0))
        if state[4]<=0:
            result['reason']='electron reversed';break
        # Test the closed exit face of the aperture we just traversed. Testing
        # only z < end can let a coarse step escape through the cylindrical wall.
        if previous_z<gun_end and math.hypot(*state[:2])>p['gun_radius_m']:
            result['reason']='gun aperture';break
        if gun_end<=previous_z<neck_end and math.hypot(*state[:2])>p['neck_radius_m']:
            result['reason']='neck aperture';break
        if z>=surface(state):
            # Bisect the final integration segment against the curved screen.
            lo,hi=0.,1.
            for _ in range(32):
                t=(lo+hi)/2
                test=[a+t*(b-a) for a,b in zip(old,state)]
                if previous_z+t*h>=surface(test):hi=t
                else:lo=t
            fraction=(lo+hi)/2
            state=[a+fraction*(b-a) for a,b in zip(old,state)]
            z=previous_z+fraction*h
            visible=abs(state[0])<=p['screen_width_m']/2 and abs(state[1])<=p['screen_height_m']/2
            result.update(landed=visible,reason='screen' if visible else 'screen clipping',x_m=state[0],y_m=state[1])
            break
        if index%5==0:points.append([z,state[0],state[1]])
    else:result['reason']='integration budget'
    points.append([z,state[0],state[1]])
    result.update(points=points,flight_s=state[5],energy_error_ev=max_error,
                  impact_energy_ev=REST_EV*(math.sqrt(1+sum(v*v for v in state[2:5]))-1))
    return collection.annotate(result)


def bundle(anode,grid2,focus,ih,iv,*,step_m=.0002,overrides=None,_ray=None):
    """Symmetric nine-ray quadrature of finite source radius and divergence.

    Separate position and angle rays avoid inventing source-angle correlation.
    The spot is an RMS estimate of this quadrature, not a fitted Gaussian PSF.
    """
    p=parameters(overrides)
    launches=[((0.,0.),(0.,0.))]
    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
        launches.append(((dx*p['source_radius_m'],dy*p['source_radius_m']),(0.,0.)))
        launches.append(((0.,0.),(dx*p['divergence_rad'],dy*p['divergence_rad'])))
    solve=ray if _ray is None else _ray
    rays=[solve(anode,grid2,focus,ih,iv,origin=o,slope=s,step_m=step_m,overrides=p) for o,s in launches]
    landed=[r for r in rays if r['landed']]
    if not landed:return dict(rays=rays,landed_fraction=0.,x_m=0.,y_m=0.,sigma_m=0.)
    x=sum(r['x_m'] for r in landed)/len(landed);y=sum(r['y_m'] for r in landed)/len(landed)
    variance=sum((r['x_m']-x)**2+(r['y_m']-y)**2 for r in landed)/(2*len(landed))
    return dict(rays=rays,landed_fraction=len(landed)/len(rays),x_m=x,y_m=y,sigma_m=math.sqrt(variance))


if __name__=='__main__':
    import argparse
    import hashlib
    import json
    from pathlib import Path
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anode',type=float,default=11000)
    parser.add_argument('--grid2',type=float,default=350)
    parser.add_argument('--focus',type=float,default=175)
    parser.add_argument('--horizontal',type=float,default=.2)
    parser.add_argument('--vertical',type=float,default=.1)
    parser.add_argument('--step',type=float,default=.0002)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('refusing to overwrite a trajectory')
    inputs=dict(anode=args.anode,grid2=args.grid2,focus=args.focus,ih=args.horizontal,iv=args.vertical)
    result=bundle(**inputs,step_m=args.step)
    report=dict(format='dac-crt-trajectory-v1',qualification='experimental-field-model',
                inputs=inputs,parameters=DEFAULTS,step_m=args.step,
                code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                point_fields=['z_m','x_m','y_m'],result=result,
                limitations=['Standalone field solver; not yet coupled to the reference circuit or museum replay.',
                             'Geometry and fields are engineering assumptions, not measured B31G22 properties.',
                             'Near-axis electrostatic expansion and prescribed yoke field; no full field solution.',
                             'No thermal emission, space charge or energy-to-phosphor calculation in this tool.'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:json.dump(report,stream,indent=2,allow_nan=False)
    print(args.output)
