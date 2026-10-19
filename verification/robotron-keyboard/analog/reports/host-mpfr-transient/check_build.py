#!/usr/bin/env python3
"""Check the compiled adapter and retain runtime build provenance."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('runtime', type=Path)
args = parser.parse_args()
root = args.runtime.resolve()
analog = Path(__file__).resolve().parents[2]
source = Path(__file__).with_name('check.c')
flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','mpfr','gmp'],text=True))
command = ['clang','-O2','-I'+str(root/'source/src/include'),'-I'+str(root/'build/src/include'),str(source),
           str(root/'build/src/maths/sparse/.libs/libsparse.a'),str(root/'build/src/misc/.libs/libmisc.a'),
           *flags,'-o',str(root/'check')]
subprocess.run(command,check=True,capture_output=True,text=True)
result = subprocess.run([str(root/'check')],check=True,capture_output=True,text=True)
libraries = {}
for package in ('mpfr','gmp'):
    directory = Path(subprocess.check_output(['pkg-config','--variable=libdir',package],text=True).strip())
    paths = list(directory.glob('lib'+package+'.dylib')) or list(directory.glob('lib'+package+'.so'))
    if len(paths) != 1: raise ValueError('Unidentified library')
    libraries[str(paths[0].resolve())] = sha(paths[0])
header = analog/'engine-patches/mpfr_linear_solver.h'
if sha(header) != sha(root/'source/src/maths/sparse/mpfr_linear_solver.h'):
    raise ValueError('Built header differs')
report = {'source':'ngspice-47', 'scope':'Experimental MPFR real linear arithmetic; binary64 stamping and integration remain unchanged',
 'basePatchSha256':sha(analog/'engine-patches/ngspice-47-linear-state-audit.patch'),
 'patchSha256':sha(analog/'engine-patches/ngspice-47-mpfr-linear.patch'),'kernelSha256':sha(header),
 'buildInputs':json.loads((root/'build-inputs.json').read_text()),
 'buildLogsSha256':{name:sha(root/name) for name in ['configure.log','make.log']},
 'executableSha256':sha(root/'build/src/ngspice'),'libraries':libraries,
 'compiler':subprocess.check_output(['clang','--version'],text=True),
 'checks':{'command':command,'sourceSha256':sha(source),'executableSha256':sha(root/'check'),
           'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},
 'equationSourceSha256':{name:sha(root/'source'/name) for name in
    ['src/maths/ni/niiter.c','src/maths/sparse/spsmp.c','src/maths/ni/niinteg.c','src/spicelib/devices/ind/indload.c']}}
(root/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print(result.stdout.strip())
