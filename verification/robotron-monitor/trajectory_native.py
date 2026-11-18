"""Explicit compiled counterpart of the Python RK4 field model; no fast math."""
import ctypes
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile
import trajectory

ROOT=Path(__file__).resolve().parent
KEYS=('screen_z_m','screen_radius_m','screen_width_m','screen_height_m','gun_radius_m',
      'neck_radius_m','yoke_start_m','yoke_length_m','horizontal_tesla_per_amp',
      'vertical_tesla_per_amp','initial_energy_ev','source_radius_m','divergence_rad',
      'grid2_length_m','focus_start_m','focus_length_m','anode_start_m','anode_length_m')
REASONS=('low acceleration','electron reversed','gun aperture','neck aperture',
         'screen','screen clipping','integration budget')


def build(directory=None):
    source=ROOT/'trajectory_native.cpp'
    flags=['-std=c++17','-O3','-fno-fast-math','-ffp-contract=off','-shared','-fPIC']
    version=subprocess.run(['c++','--version'],check=True,capture_output=True,text=True).stdout
    key=hashlib.sha256(source.read_bytes()+json.dumps([flags,version]).encode()).hexdigest()
    directory=Path(directory) if directory else ROOT.parents[1]/'build/monitor/trajectory-native'/key
    directory.mkdir(parents=True,exist_ok=True)
    library=directory/'trajectory.so';receipt=directory/'build.json'
    if library.exists():
        metadata=json.loads(receipt.read_text())
        if metadata['build_key']!=key or metadata['library_sha256']!=hashlib.sha256(library.read_bytes()).hexdigest():
            raise ValueError('compiled trajectory receipt mismatch')
    else:
        with tempfile.TemporaryDirectory(dir=directory) as tmp:
            temporary=Path(tmp)/'trajectory.so'
            subprocess.run(['c++',*flags,str(source),'-o',str(temporary)],check=True,capture_output=True,timeout=60)
            metadata=dict(build_key=key,compiler=version,flags=flags,
                          source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                          library_sha256=hashlib.sha256(temporary.read_bytes()).hexdigest())
            (Path(tmp)/'build.json').write_text(json.dumps(metadata,indent=2)+'\n')
            temporary.replace(library);(Path(tmp)/'build.json').replace(receipt)
    return library,metadata


class Backend:
    def __init__(self,directory=None):
        library,self.receipt=build(directory)
        self.library=ctypes.CDLL(str(library.resolve()))
        self.solve=self.library.crt_ray
        pointer=ctypes.POINTER(ctypes.c_double)
        self.solve.argtypes=[pointer,pointer,pointer,pointer,ctypes.c_int,ctypes.POINTER(ctypes.c_int)]
        self.solve.restype=ctypes.c_int

    def ray(self,anode,grid2,focus,ih,iv,*,origin=(0.,0.),slope=(0.,0.),step_m=.0002,overrides=None):
        p=trajectory.parameters(overrides)
        if len(origin)!=2 or len(slope)!=2:raise ValueError('invalid launch')
        values=(anode,grid2,focus,ih,iv,*origin,*slope,step_m)
        if not all(math.isfinite(v) for v in values) or not 1e-6<=step_m<=.001:
            raise ValueError('invalid ray inputs or step')
        steps=math.ceil(p['screen_z_m']/step_m)
        if steps>1000000:raise ValueError('compiled trajectory integration budget exceeded')
        count=ctypes.c_int();capacity=steps//5+5
        points=(ctypes.c_double*(3*capacity))();out=(ctypes.c_double*5)()
        reason=self.solve((ctypes.c_double*10)(*values),
                          (ctypes.c_double*18)(*(p[k] for k in KEYS)),out,points,capacity,ctypes.byref(count))
        if not 0<=reason<len(REASONS):raise ValueError('compiled trajectory failed')
        result=dict(landed=reason==4,reason=REASONS[reason],
                    points=[list(points[3*i:3*i+3]) for i in range(count.value)],
                    flight_s=out[0],energy_error_ev=out[1],impact_energy_ev=out[2])
        if reason in (4,5):result.update(x_m=out[3],y_m=out[4])
        return trajectory.collection.annotate(result)

    def bundle(self,*args,**kwargs):
        return trajectory.bundle(*args,**kwargs,_ray=self.ray)
