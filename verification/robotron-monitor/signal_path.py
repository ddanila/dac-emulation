#!/usr/bin/env python3
"""Loaded 1715W output -> cable -> K7222 input/neck characterization bench."""
import argparse,copy,json,math,re,subprocess,statistics
from pathlib import Path
import faults,lab,reference
ROOT=Path(__file__).resolve().parent
BOUNDS={ # nominal, minimum, maximum; all exploratory, not measured tolerances
 'driver_low':(.15,.05,.4),'driver_high':(4.2,2.7,5.),
 'driver_r_low':(8.,2.,30.),'driver_r_high':(35.,10.,150.),
 'driver_tau':(4e-9,1e-9,30e-9),'gate_threshold':(1.4,.8,2.),
 'gate_span':(.08,.04,.2),'gate_tau':(5e-9,1e-9,30e-9),
 'gate_input_c':(4e-12,1e-12,15e-12),
 'gate_input_high_a':(20e-6,0,50e-6),'gate_input_low_a':(-200e-6,-2e-3,-50e-6),
 'gate_low_v':(.15,.05,.2),'gate_high_headroom':(.8,.5,2.2),
 'gate_r_low':(10.,2.,10.),'gate_r_high':(80.,20.,150.),
 'gate_smooth_current':(1e-6,1e-8,1e-5),
 'gate_iq_high':(.0025,.001,.0042),'gate_iq_low':(.0065,.003,.010),
 'cable_r':(.3,.05,2.),
 'cable_c':(150e-12,30e-12,1e-9),'return_r':(.2,.02,2.),
 'contrast_trim':(1100.,22.,2200.),'contrast_r':(10000.,1000.,100000.),
 'contrast_position':(.5,.05,.95),
 'brightness_position':(.5,0.,1.),'brightness_pot_r':(10000.,5000.,10000.),
 'vertical_load':(100000.,10000.,1000000.),'sync_load':(100000.,10000.,1000000.)}
CASES=('nominal','weak-video','slow-video','cable-loading','return-resistance',
       'missing-sync','distorted-sync','stuck-intensity','receiver-video-leakage','receiver-sync-bias')
LIMITATIONS=[
 'Bounded output/input/neck bench, not a complete monitor or a specimen-validated model.',
 '74S37/T200 and discrete semiconductor models are uncalibrated functional/generic families.',
 'Cable R/C and return impedance are assumptions; no transmission-line inductance or measured cable geometry.',
 'External ideal 5/12/35/41 V and electrode supplies; the 35 V contrast/brightness feed replaces unconnected flyback/rectifier behavior in this short bench.',
 'Contrast and brightness control topologies transcribed; external potentiometer values/settings are assumptions.',
 'Horizontal phase-control and vertical oscillator loads are not connected; their input loads are explicit bounded resistors.',
 'No sync-lock, screen brightness, raster width/height or flyback diagnosis is produced.',
 'Startup uses a DC operating point at the recording initial state; not retained prior analogue history.']


def stimulus(capture,case):
    """Apply only explicit source faults; retain all independent channel edges."""
    original=capture['events'];hz=capture['clock_hz'];end=original[-1][0]
    updates={0:list(original[0][1:])};changes={}
    for channel in range(3):
        last=original[0][channel+1]
        for row in original[1:]:
            value=row[channel+1]
            if value!=last:
                t=row[0]
                if case=='distorted-sync' and channel==1 and value:
                    t+=round(.5e-6*hz)
                if t<end:changes.setdefault(t,{})[channel]=value
                last=value
    state=list(original[0][1:]);out=[]
    for t in sorted({0,end}|set(changes)):
        state=state.copy();state_update=changes.get(t,{})
        for channel,value in state_update.items():state[channel]=value
        if case=='missing-sync':state[1]=1
        if case=='stuck-intensity':state[2]=1
        if not out or state!=out[-1][1:] or t==end:out.append([t,*state])
    return out


def pwl(events,channel,hz,stop):
    # Digital controls only; finite electrical transitions are inside drivers.
    last=events[0][channel];points=[f'0 {last}']
    for row in events[1:]:
        t=row[0]/hz
        if t>stop:break
        value=row[channel]
        if value!=last:
            points.extend([f'{max(0,t-1e-10):.15g} {last}',f'{t:.15g} {value}'])
            last=value
    return 'PWL('+' '.join(points)+')'


def metrics(rows,col):
    low=min(r[col] for r in rows);high=max(r[col] for r in rows)
    result=dict(minimum=low,maximum=high,peak_to_peak=high-low)
    duration=rows[-1][0]-rows[0][0]
    result['mean']=sum((a[col]+b[col])*.5*(b[0]-a[0]) for a,b in zip(rows,rows[1:]))/duration
    if high-low<.1:
        return result|dict(rising_edges=0,falling_edges=0,period_s=None,high_width_s=None,rise_10_90_s=None)
    crossings={q:[] for q in (.1,.5,.9)}
    for a,b in zip(rows,rows[1:]):
        for q,edges in crossings.items():
            level=low+(high-low)*q
            if a[col]<level<=b[col] or a[col]>level>=b[col]:
                edges.append((a[0]+(b[0]-a[0])*(level-a[col])/(b[col]-a[col]),b[col]>a[col]))
    rising=[t for t,up in crossings[.5] if up];falling=[t for t,up in crossings[.5] if not up]
    widths=[b[0]-a[0] for a,b in zip(crossings[.5],crossings[.5][1:]) if a[1] and not b[1]]
    rise=[]
    for t,up in crossings[.1]:
        if up:
            end=next(((tt,u) for tt,u in crossings[.9] if tt>t),None)
            fall=next((tt for tt,u in crossings[.1] if tt>t and not u),math.inf)
            if end and end[1] and end[0]<fall:rise.append(end[0]-t)
    median=lambda xs:statistics.median(xs) if xs else None
    return result|dict(rising_edges=len(rising),falling_edges=len(falling),
        period_s=median([b-a for a,b in zip(rising,rising[1:])]),
        high_width_s=median(widths),rise_10_90_s=median(rise))


def run(capture_path,output,*,case='nominal',duration=.0002,step=2e-9,sections=4,changes=None):
    if case not in CASES:raise ValueError('unsupported signal-path case')
    if (sections not in (2,4,8) or not 1e-10<=step<=2e-8 or not 1e-6<=duration<=.002
            or duration/step>250000):raise ValueError('signal-path simulation budget exceeded')
    capture=lab.parse_capture(Path(capture_path))
    if capture['events'][-1][0]/capture['clock_hz']<duration:raise ValueError('capture is too short')
    if capture['format']!='dac-monitor-input-v2':
        raise ValueError('v1 remains readable in the fixture, but its sync/intensity assumptions cannot qualify this path')
    params={k:v[0] for k,v in BOUNDS.items()}
    for key,value in (changes or {}).items():
        if key not in BOUNDS or type(value) not in (int,float) or not math.isfinite(value) or not BOUNDS[key][1]<=value<=BOUNDS[key][2]:
            raise ValueError('parameter outside signal-path bound: '+key)
        params[key]=value
    import steady_supply
    brightness_top, brightness_bottom = steady_supply.brightness_resistances(
        params['brightness_position'], params['brightness_pot_r'])
    output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    status=dict(format='dac-monitor-signal-path-v1',status='incomplete',case=case,full_monitor_qualified=False)
    def save(): (output/'signal-path.json').write_text(json.dumps(status,indent=2,allow_nan=False)+'\n')
    save()
    try:
        files={name:(ROOT/name).read_bytes() for name in [
            'circuits/1715w-output.kicad_sch','circuits/k7222-11-input.kicad_sch',
            'circuits/k7222-11-neck.kicad_sch','circuits/k7222-11-sync-filter.kicad_sch','circuits/signal-path-models.cir',
            'circuits/k7222-11-neck-models.cir','circuits/k7222-11-small-transistor-models.cir',
            'reference/k7222-11/inventory.json',
            'profiles/k7222-11-neck.json','reference/1715w/output.json','sources.json','signal_path.py','lab.py','reference.py','faults.py','optics.py']}
        files['input.json']=Path(capture_path).read_bytes()
        for name,content in files.items():
            dest=output/'inputs'/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(content)
        inv=json.loads(files['reference/k7222-11/inventory.json'])
        components=[];historical=[]
        for name,board,contract in [('1715w-output',None,{'S37_DRIVER':3}),
                  ('k7222-11-input','012-6921',{'T200_BOUND':14}),('k7222-11-neck','012-6891',None),('k7222-11-sync-filter','012-6931',None)]:
            xml=output/(name+'.xml')
            lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(xml),
                str(output/'inputs/circuits'/(name+'.kicad_sch'))],output,output/(name+'.log'))
            parts=reference.source_connectivity(xml,inv if board else json.loads(files['reference/1715w/output.json']),board or '1715w',contract)
            if board:
                historical+=copy.deepcopy(parts)
                for part in parts:part['nodes']=['mreturn' if n=='0' else n for n in part['nodes']]
            components+=parts
        mutation=None
        if case.startswith('receiver-'):
            definition=(dict(target='012-6921:V7:1',operation='leakage',resistance_ohm=10)
                        if case=='receiver-video-leakage' else dict(target='012-6921:R9:2',operation='resistance_scale',factor=5))
            components,_,mutation=faults.apply(components,'',definition)
        for c in components:
            if c['reference']=='X101' and case in ('weak-video','slow-video'):
                c['value']+=' '+('resistance=8' if case=='weak-video' else 'slew=10')
        neck=reference.read_profile(ROOT/'profiles/k7222-11-neck.json')
        params|=reference.parameter_values(neck,{})
        events=stimulus(capture,case)
        (output/'effective-input.json').write_text(json.dumps(dict(capture,events=events),separators=(',',':'))+'\n')
        lines=['Loaded 1715W -> cable -> K7222 bounded receiver/neck bench']
        lines += [f'.param {k}={v:.15g}' for k,v in params.items()]
        lines += [' '.join([c['reference'],*c['nodes'],c['value']]) for c in components]
        lines += [files['circuits/k7222-11-neck-models.cir'].decode(),
                  files['circuits/k7222-11-small-transistor-models.cir'].decode(),
                  files['circuits/signal-path-models.cir'].decode()]
        for i,signal in enumerate(('video','bsyn','intens'),1):
            lines.append(f'Vlogic_{signal} logic_{signal} 0 '+pwl(events,i,capture['clock_hz'],duration))
            previous='tx_'+signal
            total_c=params['cable_c']*(10 if case=='cable-loading' else 1)
            for j in range(sections):
                node='rx_'+signal if j==sections-1 else f'cable_{signal}_{j}'
                lines += [f'Rwire_{signal}_{j} {previous} {node} {params["cable_r"]/sections}',
                          f'Cwire_{signal}_{j} {node} mreturn {total_c/sections}']
                previous=node
        lines += [f'Rreturn 0 mreturn {params["return_r"]*(50 if case=="return-resistance" else 1)}',
            'Vp5 p5 mreturn 5','Vp12 p12 mreturn 12','Vp35 p35 mreturn 35',
            'Vrail p41 mreturn 41',
            'Vg1 ug1 mreturn -25','Vg2 ug2 mreturn 350','Vg4 ug4 mreturn 175',
            'Rcontrast reference9 contrast_low {contrast_r*contrast_position}',
            f'Rbrightness_top p35 v1_base {brightness_top:.15g}',
            f'Rbrightness_bottom v1_base contrast_adjust {brightness_bottom:.15g}',
            'Rdownstream sync_c mreturn {sync_load}','Rvertical_load vertical_trigger mreturn {vertical_load}',
            'Ibeam mreturn cathode 20u','Csocket cathode mreturn {tube_cathode_c}']
        probes=[]
        for signal in ('video','bsyn','intens'):
            for location,node,ref in [('computer','tx_'+signal,'0'),('monitor','rx_'+signal,'mreturn')]:
                name=location+'_'+signal
                probes.append(dict(name=name,unit='V',expression=f'v({node},{ref})',
                    source_id=('1715w:X1:' if location=='computer' else '012-6921:X9:')+
                              ({'video':'A5','bsyn':'A3','intens':'A1'}[signal] if location=='computer' else {'video':'1','bsyn':'3','intens':'5'}[signal]),
                    id='signal-path:'+name,location=location,signal=signal,reference_point=ref))
        for name,node,sid in [('receiver_video','vid','012-6921:A1:11'),('receiver_sync','sync_gate','012-6921:A1:6'),
                ('receiver_intens','intens','012-6891:X1:7'),('sync_collector','sync_c','012-6921:V6'),
                ('vertical_filter','vf1','012-6931:C2'),('vertical_trigger','vertical_trigger','012-6931:C12'),
                ('cathode','cathode','012-6891:X2:2'),('return_offset','mreturn','cable:return')]:
            probes.append(dict(name=name,unit='V',expression=f'v({node},{"0" if name=="return_offset" else "mreturn"})',
                source_id=sid,id='signal-path:'+name,location='receiver',reference_point='computer 0' if name=='return_offset' else 'monitor return'))
        expressions=' '.join(p['name'] for p in probes)
        lets=[]
        for p in probes:
            a,b=p['expression'][2:-1].split(',')
            lets.append('let '+p['name']+' = v('+a+')'+('' if b=='0' else '-v('+b+')'))
        lines += ['.options reltol=1e-4 abstol=1e-10 vntol=1e-8 method=trap','.control',
            'set noaskquit','set wr_singlescale','set wr_vecnames','set numdgt=15',
            f'tran {step} {duration} 0 {step/2}',*lets,f'linearize {expressions}',
            f'wrdata samples.txt {expressions}','quit','.endc','.end']
        deck='\n'.join(lines)+'\n';(output/'run.cir').write_text(deck)
        log=lab.run_command(['ngspice','-b','run.cir'],output,output/'ngspice.log')
        if re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix|simulation interrupted',log):
            raise ValueError('signal-path solver diagnostics rejected')
        rows=reference.read_samples(output/'samples.txt',probes,0,duration,step)
        hashes={name:lab.digest(content) for name,content in files.items()}|{'deck':lab.digest(deck.encode())}
        signal_metrics={p['name']:metrics(rows,i+1) for i,p in enumerate(probes)}
        report=reference.package(rows,dict(name='Robotron video path: '+case,qualification='bounded-stage',
            model_id='1715w-k7222-input',components=components,probes=probes,limitations=LIMITATIONS,
            coverage=reference.coverage(inv,historical),parameters=params,uncertainty=BOUNDS,
            input={k:v for k,v in capture.items() if k!='events'},hashes=hashes,
            fault=mutation,signal_case=case,cable_sections=sections,signal_metrics=signal_metrics,
            numerical_validation='not qualified by a single run; compare timestep and cable discretization',
            solver=dict(tool='ngspice',version=subprocess.check_output(['ngspice','--version'],text=True).strip(),
                        method='trap',reltol=1e-4,abstol=1e-10,output_step_s=step,max_step_s=step/2,
                        log_sha256=lab.digest(log.encode()))),output/'replay.mcrt')
        (output/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        status.update(status='complete',parameters=params,cable_sections=sections,hashes=hashes,
            metrics=signal_metrics,limitations=LIMITATIONS,
            diagnosis='untestable: full-monitor power, deflection and thermal coupling absent')
        save();return status
    except (ValueError,OSError,subprocess.SubprocessError) as error:
        status['failure']=str(error);save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--capture',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--case',choices=CASES,default='nominal')
    p.add_argument('--duration',type=float,default=.0002);p.add_argument('--step',type=float,default=2e-9)
    p.add_argument('--sections',type=int,choices=(2,4,8),default=4);a=p.parse_args()
    print(run(a.capture,a.output,case=a.case,duration=a.duration,step=a.step,sections=a.sections)['status'])
