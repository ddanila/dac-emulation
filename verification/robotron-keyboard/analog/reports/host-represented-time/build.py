#!/usr/bin/env python3
"""Build an isolated, opt-in represented-time experiment from the integration runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
args = parser.parse_args()
base, out = args.base.resolve(), args.out.resolve()
analog = Path(__file__).resolve().parents[2]
provenance = json.loads((base/'provenance.json').read_text())
linear = provenance['baseProvenance']
for name, digest in linear['equationSourceSha256'].items():
    if name == 'src/maths/ni/niinteg.c':
        digest = provenance['integrationSourceSha256']
    if sha(base/'source'/name) != digest:
        raise ValueError('Base source differs: '+name)
for name, digest in [('src/maths/ni/mpfr_integration.h', provenance['headerSha256']),
                     ('src/maths/sparse/mpfr_linear_solver.h', linear['kernelSha256'])]:
    if sha(base/'source'/name) != digest:
        raise ValueError('Base kernel differs: '+name)
expected = json.loads((analog/'reports/host-state-trajectory/assessment.json').read_text())['sourceObservation']['sha256']
if sha(base/'source/src/spicelib/analysis/dctran.c') != expected:
    raise ValueError('Transient source differs from audited source')
header = analog/'engine-patches/represented_time_step.h'
patch = analog/'engine-patches/ngspice-47-represented-time-step.patch'
out.mkdir()
shutil.copytree(base/'source', out/'source')
(out/'build').mkdir()
shutil.copyfile(header, out/'source/src/spicelib/analysis/represented_time_step.h')
with patch.open() as stream:
    subprocess.run(['patch', '-p1'], cwd=out/'source', stdin=stream, check=True)
env = dict(os.environ)
for key in ('CPPFLAGS', 'LIBS'):
    env[key] = provenance['buildInputs'][key]
command = [str(out/'source/configure'), '--prefix='+str(out/'install'),
           '--without-x', '--with-readline=no', '--disable-openmp', '--disable-klu']
for filename, cmd in [('configure.log', command), ('make.log', ['make', '-j4'])]:
    with (out/filename).open('w') as log:
        subprocess.run(cmd, cwd=out/'build', env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
report = {'scope': 'Opt-in exact rollback and represented integration intervals; standalone analog-only experiment',
          'baseProvenanceSha256': sha(base/'provenance.json'), 'baseProvenance': provenance,
          'builderSha256': sha(__file__), 'patchSha256': sha(patch), 'headerSha256': sha(header),
          'baseTransientSourceSha256': expected,
          'transientSourceSha256': sha(out/'source/src/spicelib/analysis/dctran.c'),
          'executableSha256': sha(out/'build/src/ngspice'),
          'buildInputs': {'configure': command, 'CPPFLAGS': env['CPPFLAGS'], 'LIBS': env['LIBS']},
          'logsSha256': {name: sha(out/name) for name in ('configure.log', 'make.log')}}
(out/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
print(out/'build/src/ngspice')
