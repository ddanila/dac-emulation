"""Periodic charge collection for the explicitly reduced anode-sleeve CRT.

Unsupported trajectories retain their charge in an unresolved bucket. They are
never silently assigned to ground or converted into missing optical energy.
"""
import hashlib
import json
import math
from pathlib import Path

PROFILE = dict(format='dac-reduced-collectors-v1',id='anode-sleeve-v1',
    qualification='engineering-surrogate',specimen_validated=False,
    surfaces={'screen':'anode','screen clipping':'anode','neck aperture':'anode'},
    assumptions=['The post-gun neck/funnel is an absorbing anode-connected sleeve, not a model of real glass.',
                 'Grid-2 interception is accounted before trajectory launch.',
                 'Gun-wall, reversed and incomplete trajectories have no supported collector.'])


def annotate(result):
    result['collector']=PROFILE['surfaces'].get(result['reason'],'unresolved')
    result['collection_surface']={'screen':'phosphor','screen clipping':'offscreen-anode',
                                  'neck aperture':'anode-sleeve'}.get(result['reason'],'unsupported')
    result['terminal_position_m']=list(result['points'][-1]) if result['points'] else None
    return result


class PeriodicCollector:
    def __init__(self,period_s,*,bins,initial_energy_ev=20.):
        if not math.isfinite(period_s) or period_s<=0 or type(bins) is not int or not 4<=bins<=2000000:
            raise ValueError('invalid collector period/grid')
        if not math.isfinite(initial_energy_ev) or initial_energy_ev<0:raise ValueError('invalid launch energy')
        self.period=period_s;self.bins=bins;self.dt=period_s/bins;self.initial=initial_energy_ev
        self.charge={key:[0.]*bins for key in ('anode','unresolved')}
        self.launched=0.;self.kinetic=0.;self.work=0.;self.late=0.;self.surface_charge={}

    def add(self,launch_s,arrival_s,charge_c,kinetic_j,collector,surface):
        if not all(math.isfinite(v) for v in (launch_s,arrival_s,charge_c,kinetic_j)) or charge_c<0 or kinetic_j<0:
            raise ValueError('invalid collection packet')
        if not 0<=launch_s<=self.period or arrival_s<launch_s:raise ValueError('invalid collection time')
        if collector not in self.charge:raise ValueError('unknown collector')
        # Periodic linear hat functions integrate to dt. Splitting packet mass
        # between neighboring knots preserves charge, including boundary wraps.
        x=(arrival_s%self.period)/self.dt;i=math.floor(x);f=x-i
        self.charge[collector][i%self.bins]+=charge_c*(1-f)
        self.charge[collector][(i+1)%self.bins]+=charge_c*f
        self.launched+=charge_c;self.kinetic+=kinetic_j
        self.work+=kinetic_j-charge_c*self.initial
        self.surface_charge[surface]=self.surface_charge.get(surface,0.)+charge_c
        if arrival_s>self.period:self.late+=charge_c

    def report(self,expected_charge_c):
        if not math.isfinite(expected_charge_c) or expected_charge_c<0:raise ValueError('invalid expected emission')
        collected={k:math.fsum(v) for k,v in self.charge.items()}
        scale=max(expected_charge_c,1e-30)
        residual=abs(math.fsum(collected.values())-expected_charge_c)/scale
        unresolved=collected['unresolved']/scale
        return dict(format='dac-periodic-collection-v1',profile=PROFILE,period_s=self.period,bins=self.bins,
            emitted_charge_c=expected_charge_c,integrated_launch_charge_c=self.launched,
            collected_charge_c=collected,surface_charge_c=self.surface_charge,
            late_arrival_charge_c=self.late,periodic_in_flight_charge_change_c=0.,
            charge_relative_error=residual,unresolved_fraction=unresolved,
            charge_accepted=residual<.001 and unresolved<1e-6,
            terminal_kinetic_j=self.kinetic,launch_energy_j=self.launched*self.initial,
            trajectory_electric_work_j=self.work,
            electrical_energy_verified=False,full_monitor_qualified=False,
            currents_a={k:[q/self.dt for q in v] for k,v in self.charge.items()})


def pwl(report,collector='anode',*,scale=1.):
    validate(report)
    if not math.isfinite(scale) or scale<=0:raise ValueError('invalid PWL scale')
    values=report['currents_a'][collector];period=report['period_s'];n=len(values)
    knots=[(i,v) for i,v in enumerate(values) if i==0 or not values[i-1]==v==values[(i+1)%n]]
    knots.append((n,values[0]))
    return 'PWL('+' '.join(f'{i*period/n:.17g} {v*scale:.17g}' for i,v in knots)+') r=0'


def validate(report):
    if report.get('format')!='dac-periodic-collection-v1' or report.get('profile')!=PROFILE:
        raise ValueError('unsupported collector profile')
    n=report['bins'];period=report['period_s']
    if type(n) is not int or not 4<=n<=2000000 or not math.isfinite(period) or period<=0:raise ValueError('invalid collection grid')
    if set(report['currents_a'])!={'anode','unresolved'}:raise ValueError('missing electrode current')
    if set(report['collected_charge_c'])!={'anode','unresolved'}:raise ValueError('missing electrode charge')
    for value in (*report['collected_charge_c'].values(),report['emitted_charge_c'],report['integrated_launch_charge_c'],
                  report['unresolved_fraction'],report['charge_relative_error']):
        if not math.isfinite(value) or value<0:raise ValueError('invalid collection accounting')
    for key,values in report['currents_a'].items():
        if len(values)!=n or any(not math.isfinite(v) or v<0 for v in values):raise ValueError('invalid collector currents')
        q=math.fsum(values)*period/n
        if abs(q-report['collected_charge_c'][key])>max(q,1e-30)*1e-10:raise ValueError('collector waveform charge mismatch')
    if not report['charge_accepted'] or report['unresolved_fraction']>=1e-6 or report['charge_relative_error']>=.001:
        raise ValueError('unaccepted collector accounting')
    total=math.fsum(report['collected_charge_c'].values());expected=report['emitted_charge_c']
    if abs(total-expected)>max(expected,1e-30)*.001:raise ValueError('emitted charge mismatch')
    if abs(report['integrated_launch_charge_c']-expected)>max(expected,1e-30)*.001:raise ValueError('launch charge mismatch')
    if report['collected_charge_c']['unresolved']/max(expected,1e-30)>=1e-6:raise ValueError('unaccepted unresolved charge')


def run(trace,output,*,field=None,bins=None,step_m=.0002,max_dt_s=1/27648000):
    import beam_render
    rows=beam_render.read_trace(trace);period=rows[-1][0]-rows[0][0]
    if rows[0][0]!=0:raise ValueError('collection trace must start at zero')
    collector=PeriodicCollector(period,bins=bins or math.ceil(period/max_dt_s-1e-9),
                                initial_energy_ev=(field or {}).get('initial_energy_ev',20.))
    renderer=beam_render.Renderer(field=field,step_m=step_m,max_dt_s=max_dt_s,backend='compiled',on_collection=collector.add)
    renderer.render(rows,[0,period])
    expected=math.fsum((b[0]-a[0])*(a[-1]+b[-1])/2 for a,b in zip(rows,rows[1:]))
    report=collector.report(expected)
    report['hashes']=beam_render.model_hashes()|{'input.csv':hashlib.sha256(Path(trace).read_bytes()).hexdigest()}
    report['field_parameters']=renderer.field;report['trajectory_step_m']=step_m;report['max_interval_s']=max_dt_s
    Path(output).write_text(json.dumps(report,allow_nan=False,separators=(',',':'))+'\n')
    return report


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--trace',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--field-parameters',type=Path);p.add_argument('--bins',type=int)
    p.add_argument('--trajectory-step-m',type=float,default=.0002)
    p.add_argument('--max-interval-s',type=float,default=1/27648000)
    a=p.parse_args();r=run(a.trace,a.output,field=json.loads(a.field_parameters.read_text()) if a.field_parameters else None,
                         bins=a.bins,step_m=a.trajectory_step_m,max_dt_s=a.max_interval_s)
    print(json.dumps({k:v for k,v in r.items() if k!='currents_a'},indent=2))
