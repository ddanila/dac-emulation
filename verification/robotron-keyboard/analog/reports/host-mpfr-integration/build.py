#!/usr/bin/env python3
"""Build opt-in integration arithmetic on the verified MPFR linear runtime sources."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess

sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, required=True, help='Verified host-mpfr-transient build root')
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
base, out = args.base.resolve(), args.out.resolve()
analog = Path(__file__).resolve().parents[2]
provenance = json.loads((base/'provenance.json').read_text())
for name, digest in provenance['equationSourceSha256'].items():
    if sha(base/'source'/name) != digest:
        raise ValueError('Base equation source differs: '+name)
header = analog/'engine-patches/mpfr_integration.h'
patch = analog/'engine-patches/ngspice-47-mpfr-integration.patch'
if sha(base/'source/src/maths/sparse/mpfr_linear_solver.h') != provenance['kernelSha256']:
    raise ValueError('Base linear kernel differs')
out.mkdir()
shutil.copytree(base/'source',out/'source')
(out/'build').mkdir()
shutil.copyfile(header,out/'source/src/maths/ni/mpfr_integration.h')
with patch.open() as stream:
    subprocess.run(['patch','-p1'],cwd=out/'source',stdin=stream,check=True)
env = dict(os.environ)
for key in ('CPPFLAGS','LIBS'):
    env[key] = provenance['buildInputs'][key]
command = [str(out/'source/configure'),'--prefix='+str(out/'install'),
           '--without-x','--with-readline=no','--disable-openmp','--disable-klu']
for filename, cmd in [('configure.log',command),('make.log',['make','-j4'])]:
    with (out/filename).open('w') as log:
        subprocess.run(cmd,cwd=out/'build',env=env,stdout=log,stderr=subprocess.STDOUT,check=True)
check_source = Path(__file__).with_name('check.c')
check_command = ['cc','-O2','-I'+str(out/'source/src/include'),
                 '-I'+str(out/'build/src/include'),str(check_source),
                 str(out/'source/src/maths/ni/niinteg.c'),
                 str(out/'build/src/misc/.libs/libmisc.a'),
                 *shlex.split(env['CPPFLAGS']),*shlex.split(env['LIBS']),
                 '-o',str(out/'check')]
subprocess.run(check_command,check=True)
checks = {}
for mode in ('off','256','invalid'):
    result = subprocess.run([str(out/'check'),mode],
        env=dict(env,ROBOTRON_MPFR_INTEGRATION=mode),capture_output=True,text=True,check=True)
    checks[mode] = {'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr}
report = {'scope':'Experimental MPFR256 NIintegrate arithmetic with binary64 stored states and coefficients; opt-in and disabled-control modes',
          'adapterChecks':checks,'checkSourceSha256':sha(check_source),
          'checkExecutableSha256':sha(out/'check'),'checkCommand':check_command,
          'baseProvenanceSha256':sha(base/'provenance.json'),
          'baseProvenance':provenance, 'builderSha256':sha(Path(__file__)),
          'patchSha256':sha(patch),'headerSha256':sha(header),
          'executableSha256':sha(out/'build/src/ngspice'),
          'integrationSourceSha256':sha(out/'source/src/maths/ni/niinteg.c'),
          'buildInputs':{'configure':command,'CPPFLAGS':env['CPPFLAGS'],'LIBS':env['LIBS']},
          'logsSha256':{name:sha(out/name) for name in ('configure.log','make.log')}}
(out/'provenance.json').write_text(json.dumps(report,indent=2)+'\n')
print(out/'build/src/ngspice')
