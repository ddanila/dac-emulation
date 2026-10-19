#!/usr/bin/env python3
"""Build logging-only coverage of linear systems at represented minimum steps."""
import argparse
import copy
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
parent = json.loads((base/'provenance.json').read_text())
integration = parent['baseProvenance']
linear = integration['baseProvenance']
for name, digest in linear['equationSourceSha256'].items():
    if name == 'src/maths/ni/niinteg.c':
        digest = integration['integrationSourceSha256']
    if sha(base/'source'/name) != digest:
        raise ValueError('Base source differs: '+name)
for name, digest in [
        ('src/spicelib/analysis/dctran.c', parent['transientSourceSha256']),
        ('src/spicelib/analysis/represented_time_step.h', parent['headerSha256']),
        ('src/maths/ni/mpfr_integration.h', integration['headerSha256']),
        ('src/maths/sparse/mpfr_linear_solver.h', linear['kernelSha256'])]:
    if sha(base/'source'/name) != digest:
        raise ValueError('Base source differs: '+name)
patch = analog/'engine-patches/ngspice-47-represented-linear-audit.patch'
out.mkdir()
shutil.copytree(base/'source', out/'source')
(out/'build').mkdir()
with patch.open() as stream:
    subprocess.run(['patch', '-p1'], cwd=out/'source', stdin=stream, check=True)
env = dict(os.environ)
for key in ('CPPFLAGS', 'LIBS'):
    env[key] = parent['buildInputs'][key]
command = [str(out/'source/configure'), '--prefix='+str(out/'install'),
           '--without-x', '--with-readline=no', '--disable-openmp', '--disable-klu']
for filename, cmd in [('configure.log', command), ('make.log', ['make', '-j4'])]:
    with (out/filename).open('w') as log:
        subprocess.run(cmd, cwd=out/'build', env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
# Keep the represented-time provenance shape for its runner, while explicitly
# replacing the build identity and retaining the complete pre-audit build receipt.
report = copy.deepcopy(parent)
report.update(scope=__doc__, builderSha256=sha(__file__),
              auditBaseProvenance=parent, auditBaseProvenanceSha256=sha(base/'provenance.json'),
              auditPatchSha256=sha(patch),
              auditedLinearSourceSha256=sha(out/'source/src/maths/ni/niiter.c'),
              executableSha256=sha(out/'build/src/ngspice'),
              buildInputs={'configure': command, 'CPPFLAGS': env['CPPFLAGS'], 'LIBS': env['LIBS']},
              logsSha256={name: sha(out/name) for name in ('configure.log', 'make.log')})
(out/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
print(out/'build/src/ngspice')
