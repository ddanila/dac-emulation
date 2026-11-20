#!/usr/bin/env python3
"""Stream a bounded electrical CSV through physical optics to disk.

This is an optical-bench entry point. It cannot qualify a full monitor, infer
thermal equilibrium, or turn a partial solver run into a complete recording.
"""
import argparse
import array
from file_hash import digest as file_digest
import json
from pathlib import Path
import shutil
import struct
import sys
import beam_render as beam
import phosphor




def run(trace,output,frame_times,*,surface=None,backend='compiled',row_budget=100000000,
        bundle_budget=100000000,duration_budget_s=1.,byte_budget=16*1024**3):
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    result=dict(status='incomplete',qualification='experimental-optical-bench',full_monitor_qualified=False)
    def save():(output/'render.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    save()
    try:
        frame_times=tuple(frame_times)
        if len(frame_times)<2 or frame_times[-1]-frame_times[0]>1:
            raise ValueError('replay window must span at most one second')
        trace=Path(trace)
        if trace.stat().st_size>byte_budget:raise ValueError('trace file budget exceeded')
        before=file_digest(trace);shutil.copyfile(trace,output/'input.csv')
        if file_digest(output/'input.csv')!=before:raise ValueError('electrical trace changed during import')
        hashes={'input.csv':before}
        for name,digest in (beam.model_hashes()|{'stream_render.py':file_digest(__file__)}).items():
            shutil.copyfile(Path(beam.__file__).parent/name,output/name);hashes[name]=digest
        renderer=beam.Renderer(surface=surface,backend=backend,bundle_budget=bundle_budget)
        chunks=[];payload_bytes=0;frame_count=0;preview=[];stride=1;row_count=0;last=None;linear_frames=[]
        with (output/'payload.pending').open('xb') as payload:
            def append(data,description):
                nonlocal payload_bytes
                if payload_bytes+len(data)>63*1024**2:raise ValueError('replay payload budget exceeded')
                chunks.append(description|dict(offset=payload_bytes,bytes=len(data),sha256=beam.digest(data)))
                payload.write(data);payload_bytes+=len(data)
            def frame_sink(frame):
                nonlocal frame_count
                w,h=renderer.surface.p['width'],renderer.surface.p['height']
                phosphor.png(output/f'frame-{frame_count:03d}.png',w,h,frame['display'])
                linear=array.array('f',frame['linear'])
                if sys.byteorder!='little':linear.byteswap()
                with (output/f'frame-{frame_count:03d}.f32').open('xb') as stream:stream.write(linear.tobytes())
                linear_frames.append(dict(path=f'frame-{frame_count:03d}.f32',time_s=frame['time'],
                    sha256=file_digest(output/f'frame-{frame_count:03d}.f32')))
                append(frame['display'],dict(kind='frame',width=w,height=h,time=frame['time']))
                frame_count+=1
            def rows():
                nonlocal stride,row_count,last,preview
                for row in beam.iter_trace(output/'input.csv',byte_budget=byte_budget,row_budget=row_budget,
                                           duration_budget_s=duration_budget_s):
                    if row_count%stride==0:preview.append(row)
                    if len(preview)>125000:preview=preview[::2];stride*=2
                    last=row;row_count+=1
                    yield row
            renderer.render_stream(rows(),frame_times,on_frame=frame_sink,row_budget=row_budget,
                                   duration_budget_s=duration_budget_s)
            if preview[-1]!=last:preview.append(last)
            values=array.array('d',(v for row in preview for v in row))
            if sys.byteorder!='little':values.byteswap()
            append(values.tobytes(),dict(kind='trace',rows=len(preview),fields=[
                dict(name=n,unit=u,source_id='electrical-trace:'+n) for n,u in zip(beam.FIELDS,beam.UNITS)]))
        p=renderer.surface.p
        metadata=dict(format='dac-crt-replay',version=3,name='Streamed electrical trace → optics → phosphor',
            qualification='experimental-optical-bench',model_id='crt-electrical-optical-backend',
            full_monitor_qualified=False,start_time=preview[0][0],end_time=last[0],duration=last[0]-preview[0][0],
            components=[],limitations=beam.LIMITATIONS,render=renderer.report(),rays=renderer.rays,chunks=chunks,
            hashes=hashes,display=dict(transfer='srgb',exposure_m2_per_w=p['exposure_m2_per_w'],
                screen_width_m=p['screen_width_m'],screen_height_m=p['screen_height_m'],pixel_aspect=1,
                screen_scale_pixels_per_m=renderer.surface.scale,
                comparison_key=beam.digest(json.dumps(p,sort_keys=True).encode())))
        header=json.dumps(metadata,separators=(',',':'),allow_nan=False).encode()
        if len(header)>1024**2 or 12+len(header)+payload_bytes>64*1024**2:raise ValueError('replay budget exceeded')
        with (output/'replay.pending').open('xb') as stream:
            stream.write(b'DACCRT3\n'+struct.pack('<I',len(header))+header)
            with (output/'payload.pending').open('rb') as payload:shutil.copyfileobj(payload,stream)
        state=renderer.checkpoint()
        with (output/'optical-state.json').open('x') as stream:json.dump(state,stream,separators=(',',':'),allow_nan=False)
        result.update(status='complete',frames=frame_count,electrical_rows=row_count,preview_rows=len(preview),
                      hashes=hashes,render=renderer.report(),limitations=beam.LIMITATIONS,
                      linear_frames=linear_frames,surface_parameters=p.copy(),
                      linear_format=dict(dtype='little-endian float32',unit='W/m^2',order='row-major',width=p['width'],height=p['height']))
        save();(output/'replay.pending').rename(output/'replay.mcrt')
        (output/'payload.pending').unlink()
        return result
    except Exception as error:
        result.update(status='incomplete',failure=str(error));save();raise


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frame-times',type=Path,required=True,help='JSON array of absolute SI times, spanning the trace')
    p.add_argument('--backend',choices=('python','compiled'),default='compiled')
    p.add_argument('--duration-budget',type=float,default=1.)
    a=p.parse_args();run(a.trace,a.output,json.loads(a.frame_times.read_text()),backend=a.backend,duration_budget_s=a.duration_budget)
