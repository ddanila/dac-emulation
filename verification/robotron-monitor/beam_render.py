#!/usr/bin/env python3
"""Render electrode/yoke solutions through trajectories and phosphor.

This optical backend is not a full-monitor circuit solver. A trace must supply
beam current entering the modeled gun (after any separately modeled grid capture),
not an already screen-clipped current. No framebuffer or raster coordinates enter.
Unqualified inputs remain explicitly optical-bench recordings.
"""
import argparse,array,csv,functools,hashlib,heapq,json,math,struct,subprocess,sys
from pathlib import Path
import phosphor,trajectory

FIELDS=('time','anode_v','grid2_v','focus_v','cathode_v','horizontal_a','vertical_a','beam_a')
UNITS=('s','V','V','V','V','A','A','A')
LIMITATIONS=[
 'Optical backend only: electrical trace provenance does not establish complete monitor circuitry.',
 'Reduced parameterized gun/yoke fields and nine-ray source quadrature; not a measured B31G22 field solution.',
 'Phosphor efficiency, decay, geometry and exposure are engineering assumptions; optical power is not calibrated luminance.',
 'Piecewise-linear electrical input must resolve video/switching events; rendering cannot recover missing bandwidth.',
 'Current is defined at the modeled gun entrance, after separately modeled grid capture; no framebuffer pixels or prescribed raster positions.',
 'No full-monitor warm-up, flyback or capacitor diagnosis is qualified by this backend.']


def digest(data):return hashlib.sha256(data).hexdigest()


def model_hashes():
    return {name:digest((Path(__file__).parent/name).read_bytes())
            for name in ('beam_render.py','trajectory.py','trajectory_native.py','trajectory_native.cpp','phosphor.py','optics.py')}


def iter_trace(path, *, byte_budget=256*1024*1024, row_budget=1000000, duration_budget_s=1.):
    """Validate SI samples incrementally. Explicit budgets also cover streamed files."""
    if Path(path).stat().st_size>byte_budget:raise ValueError('trace file budget exceeded')
    with Path(path).open(newline='') as stream:
        reader=csv.reader(stream)
        if tuple(next(reader,()))!=FIELDS:raise ValueError('unexpected electrical trace fields')
        yield from validated_rows((tuple(float(v) for v in fields) for fields in reader),
                                  row_budget=row_budget,duration_budget_s=duration_budget_s)


def validated_rows(rows, *, row_budget, duration_budget_s):
    if type(row_budget) is not int or not 2<=row_budget<=100000000:
        raise ValueError('invalid electrical row budget')
    if not math.isfinite(duration_budget_s) or not 0<duration_budget_s<=3600:
        raise ValueError('invalid electrical duration budget')
    first=previous=None;count=0
    for raw in rows:
        row=tuple(raw);count+=1
        if count>row_budget:raise ValueError('trace row budget exceeded')
        if len(row)!=len(FIELDS) or not all(math.isfinite(v) and abs(v)<=1e12 for v in row):
            raise ValueError('invalid electrical sample')
        if not 0<=row[0]<=3600 or row[-1]<0 or previous is not None and row[0]<=previous:
            raise ValueError('invalid electrical time/current')
        if first is None:first=row[0]
        if row[0]-first>duration_budget_s:raise ValueError('electrical duration budget exceeded')
        previous=row[0]
        yield row
    if count<2:raise ValueError('expected at least two electrical samples')


def read_trace(path):
    return list(iter_trace(path))


class Renderer:
    def __init__(self,*,surface=None,field=None,step_m=.0002,max_dt_s=1/27648000,
                 movement_pixels=.25,bundle_budget=2000000,continuation=None,backend="python"):
        if backend not in ('python','compiled'):raise ValueError('unknown trajectory backend')
        self.backend=backend;self.native=None
        if backend=='compiled':
            import trajectory_native
            self.native=trajectory_native.Backend()
        self.surface=phosphor.Surface(surface);self.field=trajectory.parameters(field)
        for key in ('screen_width_m','screen_height_m','screen_radius_m'):
            if self.surface.p[key]!=self.field[key]:raise ValueError('electrical/optical screen geometry mismatch')
        if not 1e-6<=step_m<=.001 or not 1e-10<=max_dt_s<=.001 or not 0<movement_pixels<=.5:
            raise ValueError('invalid optical resolution')
        if type(bundle_budget) is not int or not 1<=bundle_budget<=100000000:raise ValueError('invalid ray budget')
        self.step_m=step_m;self.max_dt=max_dt_s;self.movement=movement_pixels;self.budget=bundle_budget
        self.bundles=0;self.events=[];self.serial=0;self.frames=[];self.rays=[]
        self.started=False;self.completed=False;self.window_start_s=None
        self.incident_j=0.;self.intercepted_j=0.;self.max_energy_error_ev=0.;self.samples=0
        self._bundle=functools.lru_cache(maxsize=512)(self._solve)
        self.continuation=continuation is not None;self.last_row=None
        if continuation is not None:self._restore(continuation)

    def _restore(self,state):
        settings=dict(field=self.field,step_m=self.step_m,max_dt_s=self.max_dt,movement_pixels=self.movement,backend=self.backend)
        if state.get('format')!='dac-optical-state-v1' or state.get('settings')!=settings or state.get('model_hashes')!=model_hashes():
            raise ValueError('incompatible optical continuation')
        restored=phosphor.Surface.restore(state['surface'])
        if restored.p!=self.surface.p:raise ValueError('incompatible phosphor continuation')
        row=state['last_electrical_row']
        if len(row)!=len(FIELDS) or not all(math.isfinite(v) and abs(v)<=1e12 for v in row) or row[0]!=restored.time or row[-1]<0:
            raise ValueError('invalid continuation boundary')
        events=state['arrivals']
        if len(events)>1000000:raise ValueError('arrival budget exceeded')
        for event in events:
            if len(event)!=4 or not all(math.isfinite(v) for v in event) or event[0]<restored.time or event[-1]<0:
                raise ValueError('invalid continuation arrival')
            self.serial+=1;heapq.heappush(self.events,(event[0],self.serial,*event[1:]))
        ledger=state['kinetic_energy']
        if set(ledger)!={'terminal_j','intercepted_j'} or any(not math.isfinite(v) or v<0 for v in ledger.values()):
            raise ValueError('invalid kinetic energy ledger')
        self.incident_j=ledger['terminal_j'];self.intercepted_j=ledger['intercepted_j']
        accounted=self.intercepted_j+sum(e[-1] for e in self.events)+(restored.deposited_j+restored.clipped_j)/restored.p['efficiency']
        if abs(accounted-self.incident_j)>max(self.incident_j,1e-30)*1e-8:raise ValueError('inconsistent kinetic energy ledger')
        self.surface=restored;self.last_row=tuple(row)

    def checkpoint(self):
        if not self.completed or self.last_row is None:raise ValueError('no completed optical window')
        return dict(format='dac-optical-state-v1',model_hashes=model_hashes(),settings=dict(field=self.field.copy(),step_m=self.step_m,max_dt_s=self.max_dt,movement_pixels=self.movement,backend=self.backend),
                    surface=self.surface.checkpoint(),last_electrical_row=list(self.last_row),
                    arrivals=[[e[0],*e[2:]] for e in sorted(self.events)],
                    kinetic_energy=dict(terminal_j=self.incident_j,intercepted_j=self.intercepted_j))

    def _solve(self,anode,g2,focus,ih,iv):
        self.bundles+=1
        if self.bundles>self.budget:raise ValueError('trajectory budget exceeded; no accepted render')
        solve=trajectory.bundle if self.native is None else self.native.bundle
        result=solve(anode,g2,focus,ih,iv,step_m=self.step_m,overrides=self.field)
        for ray in result['rays']:
            if ray['reason']=='integration budget':raise ValueError('trajectory did not finish')
            if ray['energy_error_ev']>max(1.,.01*ray['impact_energy_ev']):raise ValueError('trajectory energy error exceeded')
            self.max_energy_error_ev=max(self.max_energy_error_ev,ray['energy_error_ev'])
        return result

    def bundle(self,row):
        # All electrode potentials share one electrical reference. The trajectory
        # model begins at cathode potential zero; subtract it exactly once.
        return self._bundle(row[1]-row[4],row[2]-row[4],row[3]-row[4],row[5],row[6])

    def _drain(self,time):
        while self.events and self.events[0][0]<=time:
            when,_,x,y,joules=heapq.heappop(self.events)
            self.surface.deposit(when,x,y,joules)

    def _segment(self,a,b,depth=0):
        dt=b[0]-a[0];mid=tuple((x+y)/2 for x,y in zip(a,b))
        if max(a[-1],b[-1])==0:return
        if depth>32:raise ValueError('optical subdivision did not converge')
        if dt>self.max_dt:
            self._segment(a,mid,depth+1);self._segment(mid,b,depth+1);return
        left,center,right=(self.bundle(r) for r in (a,mid,b))
        scale=(self.surface.scale,self.surface.scale)
        displacement=0.;changed=False
        for ra,rm,rb in zip(left['rays'],center['rays'],right['rays']):
            changed |= len({r['landed'] for r in (ra,rm,rb)})>1
            if all(r['landed'] for r in (ra,rm,rb)):
                displacement=max(displacement,math.hypot((ra['x_m']-rb['x_m'])*scale[0],(ra['y_m']-rb['y_m'])*scale[1]),
                                 2*math.hypot((rm['x_m']-(ra['x_m']+rb['x_m'])/2)*scale[0],(rm['y_m']-(ra['y_m']+rb['y_m'])/2)*scale[1]))
        # Resolve physical pixel crossings before depositing a midpoint ray.
        # Pixel area integration must not acquire a resolution-dependent blur.
        crossed=any(self.surface.cell(ra['x_m'],ra['y_m'])!=self.surface.cell(rb['x_m'],rb['y_m'])
                    or self.surface.cell(ra['x_m'],ra['y_m'])!=self.surface.cell(rm['x_m'],rm['y_m'])
                    for ra,rm,rb in zip(left['rays'],center['rays'],right['rays'])
                    if all(r['landed'] for r in (ra,rm,rb)))
        if (changed or crossed or displacement>self.movement) and dt>1e-12:
            self._segment(a,mid,depth+1);self._segment(mid,b,depth+1);return
        self.samples+=1
        for ray in center['rays']:
            joules=mid[-1]*dt*max(ray['impact_energy_ev'],0)/len(center['rays'])
            self.incident_j+=joules
            if ray['landed']:
                self.serial+=1
                heapq.heappush(self.events,(mid[0]+ray['flight_s'],self.serial,ray['x_m'],ray['y_m'],joules))
                if len(self.events)>1000000:raise ValueError('arrival budget exceeded')
            else:self.intercepted_j+=joules
        # Ordered arrivals account for flight time without shifting the input clock.
        self._drain(a[0])

    def render(self,rows,frame_times):
        if not 2<=len(rows)<=1000000:raise ValueError('invalid electrical row count')
        return self.render_stream(iter(rows),frame_times)

    def render_stream(self,rows,frame_times,*,on_frame=None,row_budget=1000000,duration_budget_s=1.):
        """Consume accepted samples once, retaining two rows and pending arrivals.

        With on_frame, frames are delivered synchronously and are not retained.
        Completion is recorded only after EOF and the requested endpoint agree.
        A consumer must not publish frames from an incomplete run as accepted.
        """
        if self.started:raise ValueError('renderer already used')
        self.started=True
        times=tuple(frame_times)
        if len(times)<2 or len(times)>120 or not all(math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):
            raise ValueError('invalid frame times')
        frame_bytes=self.surface.p['width']*self.surface.p['height']*5
        if (len(times) if on_frame is None else 1)*frame_bytes>64*1024*1024:
            raise ValueError('frame budget exceeded')
        source=iter(validated_rows(rows,row_budget=row_budget,duration_budget_s=duration_budget_s))
        a=next(source);b=next(source)
        self.window_start_s=a[0]
        if times[0]!=a[0]:raise ValueError('frame times must span the electrical window')
        if self.continuation:
            if a!=self.last_row:raise ValueError('electrical continuation boundary mismatch')
        else:self.surface=phosphor.Surface(self.surface.p,start_s=a[0])
        for ft in times:
            while a[0]<ft:
                if b is None:raise ValueError('electrical trace ended before requested frame')
                stop=min(b[0],ft)
                if stop==b[0]:cut=b
                else:
                    fraction=(stop-a[0])/(b[0]-a[0])
                    cut=(stop,*(x+fraction*(y-x) for x,y in zip(a[1:],b[1:])))
                self._segment(a,cut);a=cut
                if stop==b[0]:b=next(source,None)
            self._drain(ft)
            linear,display=self.surface.snapshot(ft)
            frame=dict(time=ft,linear=linear,display=display)
            if on_frame is None:self.frames.append(frame)
            else:on_frame(frame)
            if len(self.rays)<32:
                ray=self.bundle(a)['rays'][0]
                self.rays.append(dict(time=ft,landed=ray['landed'],reason=ray['reason'],points=ray['points']))
        if b is not None:raise ValueError('electrical trace extends beyond requested frames')
        self.last_row=a;self.completed=True
        return self.frames

    def report(self):
        return dict(parameters=self.surface.p,field_parameters=self.field,trajectory_step_m=self.step_m,
                    backend=self.backend,backend_build=None if self.native is None else self.native.receipt,
                    max_interval_s=self.max_dt,movement_limit_pixels=self.movement,bundles=self.bundles,
                    optical_continuation=self.continuation,emission_intervals=self.samples,energy=self.surface.balance()|dict(
                        terminal_kinetic_j=self.incident_j,intercepted_kinetic_j=self.intercepted_j,
                        in_flight_kinetic_j=sum(e[-1] for e in self.events)),max_trajectory_energy_error_ev=self.max_energy_error_ev)


def package(path,rows,renderer,metadata):
    """V3 optical-bench replay. This API cannot assert full-monitor qualification."""
    chunks=[];payload=bytearray()
    def append(data,description):
        chunks.append(description|dict(offset=len(payload),bytes=len(data),sha256=digest(data)));payload.extend(data)
    for frame in renderer.frames:
        append(frame['display'],dict(kind='frame',width=renderer.surface.p['width'],height=renderer.surface.p['height'],time=frame['time']))
    # Trace reduction affects viewer probes only, never optical integration.
    stride=max(1,math.ceil((len(rows)-1)/250000));preview=rows[::stride]
    if preview[-1]!=rows[-1]:preview.append(rows[-1])
    values=array.array('d',(v for row in preview for v in row))
    if sys.byteorder!='little':values.byteswap()
    append(values.tobytes(),dict(kind='trace',rows=len(preview),fields=[dict(name=n,unit=u,source_id='electrical-trace:'+n) for n,u in zip(FIELDS,UNITS)]))
    report=metadata|dict(format='dac-crt-replay',version=3,name='Electrical trace → electron optics → phosphor',
        qualification='experimental-optical-bench',model_id='crt-electrical-optical-backend',
        full_monitor_qualified=False,start_time=rows[0][0],end_time=rows[-1][0],duration=rows[-1][0]-rows[0][0],
        components=[],limitations=LIMITATIONS,render=renderer.report(),rays=renderer.rays,chunks=chunks,
        display=dict(transfer='srgb',exposure_m2_per_w=renderer.surface.p['exposure_m2_per_w'],
                     screen_width_m=renderer.surface.p['screen_width_m'],screen_height_m=renderer.surface.p['screen_height_m'],
                     pixel_aspect=1,screen_scale_pixels_per_m=renderer.surface.scale,
                     comparison_key=digest(json.dumps(renderer.surface.p,sort_keys=True).encode())))
    header=json.dumps(report,separators=(',',':'),allow_nan=False).encode()
    if len(header)>1024*1024 or 12+len(header)+len(payload)>64*1024*1024:raise ValueError('replay budget exceeded')
    with Path(path).open('xb') as stream:stream.write(b'DACCRT3\n'+struct.pack('<I',len(header))+header+payload)
    return report


def run(trace,output,*,frame_count=2,step_m=.0002,max_dt_s=1/27648000,surface=None,state_path=None,backend="python"):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result=dict(status='incomplete',qualification='experimental-optical-bench',full_monitor_qualified=False)
    def save():(output/'render.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    save()
    try:
        if type(frame_count) is not int or not 2<=frame_count<=120:raise ValueError('invalid frame count')
        rows=read_trace(trace);source=Path(trace).read_bytes();(output/'input.csv').write_bytes(source)
        inputs={name:(Path(__file__).parent/name).read_bytes() for name in ('beam_render.py','trajectory.py','trajectory_native.py','trajectory_native.cpp','phosphor.py','optics.py')}
        for name,data in inputs.items():(output/name).write_bytes(data)
        continuation=None
        if state_path is not None:
            if Path(state_path).stat().st_size>64*1024*1024:raise ValueError('state file budget exceeded')
            raw=Path(state_path).read_bytes();continuation=json.loads(raw)
            (output/'input-state.json').write_bytes(raw);inputs['input-state.json']=raw
        renderer=Renderer(surface=surface,step_m=step_m,max_dt_s=max_dt_s,continuation=continuation,backend=backend)
        start,end=rows[0][0],rows[-1][0]
        times=[start+(end-start)*i/(frame_count-1) for i in range(frame_count)];times[-1]=end
        renderer.render(rows,times)
        state=json.dumps(renderer.checkpoint(),separators=(',',':'),allow_nan=False).encode()
        if len(state)>64*1024*1024:raise ValueError('state file budget exceeded')
        (output/'optical-state.json').write_bytes(state)
        hashes={name:digest(data) for name,data in inputs.items()}|{'input.csv':digest(source)}
        for i,frame in enumerate(renderer.frames):
            phosphor.png(output/f'frame-{i:03d}.png',renderer.surface.p['width'],renderer.surface.p['height'],frame['display'])
            linear=frame['linear']
            if sys.byteorder!='little':linear.byteswap()
            with (output/f'frame-{i:03d}.f32').open('xb') as stream:stream.write(linear.tobytes())
        report=package(output/'replay.pending',rows,renderer,dict(hashes=hashes))
        result.update(status='complete',hashes=hashes,render=renderer.report(),limitations=LIMITATIONS,
                      linear_format=dict(dtype='little-endian float32',unit='W/m^2',order='row-major',width=renderer.surface.p['width'],height=renderer.surface.p['height']))
        save()
        (output/'replay.pending').rename(output/'replay.mcrt')
        return report
    except (ValueError,OSError,ArithmeticError,KeyError,TypeError,subprocess.SubprocessError) as error:
        result.update(status='incomplete',failure=str(error));save();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--trace',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--frames',type=int,default=2);parser.add_argument('--trajectory-step',type=float,default=.0002)
    parser.add_argument('--max-interval',type=float,default=1/27648000)
    parser.add_argument('--state',type=Path,help='Optical continuation only; not electrical/thermal solver state')
    parser.add_argument('--backend',choices=('python','compiled'),default='python')
    args=parser.parse_args();run(args.trace,args.output,frame_count=args.frames,step_m=args.trajectory_step,max_dt_s=args.max_interval,state_path=args.state,backend=args.backend)
