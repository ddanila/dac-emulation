"""Energy-accounted phosphor surface, independent of raster timing or pixels.

Stored state is optical excitation energy in joules per projected-screen cell.
Emission follows a single exponential. Efficiency, decay and exposure are bounded
engineering assumptions, not B31G22 calibration. Display conversion never auto-scales.
"""
import array, math, struct, sys, zlib
from pathlib import Path

DEFAULTS = dict(width=640, height=480, screen_width_m=.210, screen_height_m=.145,
                screen_radius_m=.45, tau_s=.025, efficiency=.08, exposure_m2_per_w=.02)


def parameters(changes=None):
    p=DEFAULTS | (changes or {})
    if set(p)!=set(DEFAULTS):raise ValueError('unknown phosphor parameter')
    for name in ('width','height'):
        if type(p[name]) is not int or not 8<=p[name]<=2048:raise ValueError('invalid image size')
    if p['width']*p['height']>1048576:raise ValueError('image pixel budget exceeded')
    for name in set(p)-{'width','height'}:
        if type(p[name]) not in (int,float) or not math.isfinite(p[name]) or p[name]<=0:
            raise ValueError('invalid phosphor parameter: '+name)
    if not 1e-6<=p['tau_s']<=10 or p['efficiency']>1:raise ValueError('invalid phosphor response')
    if math.hypot(p['screen_width_m']/2,p['screen_height_m']/2)>=p['screen_radius_m']:
        raise ValueError('screen outside curvature radius')
    return p


def png(path,width,height,pixels):
    """8-bit grayscale PNG using only the standard library."""
    if len(pixels)!=width*height:raise ValueError('invalid PNG payload')
    def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    data=b''.join(b'\x00'+pixels[y*width:(y+1)*width] for y in range(height))
    with Path(path).open('xb') as out:
        out.write(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,0,0,0,0)))
        out.write(chunk(b'IDAT',zlib.compress(data))+chunk(b'IEND',b''))


class Surface:
    def __init__(self,changes=None,*,start_s=0.):
        self.p=parameters(changes)
        if not math.isfinite(start_s) or start_s<0:raise ValueError('invalid start time')
        self.time=start_s;self.energy=array.array('d',[0.])*(self.p['width']*self.p['height'])
        self.last=array.array('d',[start_s])*len(self.energy)
        self.deposited_j=0.;self.clipped_j=0.;self.emitted_j=0.
        # Spherical-area correction to projected screen pixels.
        w,h=self.p['width'],self.p['height'];sw,sh=self.p['screen_width_m'],self.p['screen_height_m']
        radius=self.p['screen_radius_m'];self.scale=min(w/sw,h/sh);flat=1/self.scale**2
        def area(x,y):
            xx,yy=(x+.5-w/2)/self.scale,(h/2-y-.5)/self.scale
            # Letterbox cells are never illuminated and need no sphere geometry.
            if abs(xx)>sw/2 or abs(yy)>sh/2:return flat
            return flat*radius/math.sqrt(radius*radius-xx*xx-yy*yy)
        self.areas=array.array('d',(area(x,y) for y in range(h) for x in range(w)))

    def _decay(self,index,time):
        old=self.energy[index];new=old*math.exp(-(time-self.last[index])/self.p['tau_s'])
        self.emitted_j+=old-new;self.energy[index]=new;self.last[index]=time

    def deposit(self,time,x,y,impact_j):
        if not all(math.isfinite(v) for v in (time,x,y,impact_j)) or time<self.time or impact_j<0:
            raise ValueError('invalid deposition event')
        self.time=time
        optical=impact_j*self.p['efficiency']
        w,h=self.p['width'],self.p['height']
        # Bilinear area assignment preserves energy, including edge losses.
        px=x*self.scale+w/2-.5;py=h/2-y*self.scale-.5
        ix,iy=math.floor(px),math.floor(py);fx,fy=px-ix,py-iy
        retained=0.
        for xx,wx in ((ix,1-fx),(ix+1,fx)):
            for yy,wy in ((iy,1-fy),(iy+1,fy)):
                part=optical*wx*wy
                if (0<=xx<w and 0<=yy<h and abs((xx+.5-w/2)/self.scale)<=self.p['screen_width_m']/2
                    and abs((h/2-yy-.5)/self.scale)<=self.p['screen_height_m']/2):
                    i=yy*w+xx;self._decay(i,time);self.energy[i]+=part;retained+=part
        self.deposited_j+=retained;self.clipped_j+=optical-retained
        return retained

    def snapshot(self,time):
        if not math.isfinite(time) or time<self.time:raise ValueError('nonmonotonic phosphor time')
        self.time=time
        for i in range(len(self.energy)):self._decay(i,time)
        # Emitted optical power per curved surface area, not calibrated luminance.
        linear=array.array('f',(e/(self.p['tau_s']*a) for e,a in zip(self.energy,self.areas)))
        exposure=self.p['exposure_m2_per_w']
        def srgb(v):return 12.92*v if v<=.0031308 else 1.055*v**(1/2.4)-.055
        display=bytes(round(255*srgb(min(1,max(0,v*exposure)))) for v in linear)
        return linear,display

    def balance(self):
        return dict(deposited_optical_j=self.deposited_j,clipped_optical_j=self.clipped_j,
                    emitted_optical_j=self.emitted_j,stored_optical_j=sum(self.energy))

    def export(self,path,time):
        path=Path(path);linear,display=self.snapshot(time)
        if sys.byteorder!='little':linear.byteswap()
        with path.with_suffix('.f32').open('xb') as out:out.write(linear.tobytes())
        png(path.with_suffix('.png'),self.p['width'],self.p['height'],display)
        return display
