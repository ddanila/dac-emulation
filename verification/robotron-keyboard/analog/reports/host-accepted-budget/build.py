#!/usr/bin/env python3
"""Add an opt-in accepted-point capture budget to the experimental assembly runtime."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--base', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
base, out = a.base.resolve(), a.out.resolve()
analog = Path(__file__).resolve().parents[2]
parent = json.loads((base/'provenance.json').read_text())
for key, name in [('assemblyPatchSha256', 'ngspice-47-capacitor-assembly.patch'),
                  ('assemblyHeaderSha256', 'capacitor_assembly.h')]:
    if parent[key] != sha(analog/'engine-patches'/name):
        raise ValueError('Assembly source differs: '+name)
for key, name in [('transientSourceSha256', 'src/spicelib/analysis/dctran.c'),
                  ('auditedLinearSourceSha256', 'src/maths/ni/niiter.c'),
                  ('auditedCapacitorSourceSha256', 'src/spicelib/devices/cap/capload.c')]:
    if parent[key] != sha(base/'source'/name):
        raise ValueError('Base source differs: '+name)
if parent['executableSha256'] != sha(base/'build/src/ngspice'):
    raise ValueError('Base executable differs')
patch = analog/'engine-patches/ngspice-47-accepted-budget.patch'
header = analog/'engine-patches/accepted_budget.h'
out.mkdir()
shutil.copytree(base/'source', out/'source')
shutil.copy2(header, out/'source/src/spicelib/analysis'/header.name)
with patch.open() as stream:
    subprocess.run(['patch', '-p1'], cwd=out/'source', stdin=stream, check=True)
(out/'build').mkdir()
env = dict(os.environ)
for key in ('CPPFLAGS', 'LIBS'):
    env[key] = parent['buildInputs'][key]
command = [str(out/'source/configure'), '--prefix='+str(out/'install'),
           '--without-x', '--with-readline=no', '--disable-openmp', '--disable-klu']
for name, cmd in [('configure.log', command), ('make.log', ['make', '-j4'])]:
    with (out/name).open('w') as log:
        subprocess.run(cmd, cwd=out/'build', env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
report = dict(parent)
report.update(budgetBaseProvenance=parent, budgetBaseProvenanceSha256=sha(base/'provenance.json'),
              budgetPatchSha256=sha(patch), budgetHeaderSha256=sha(header),
              builderSha256=sha(__file__), executableSha256=sha(out/'build/src/ngspice'),
              transientSourceSha256=sha(out/'source/src/spicelib/analysis/dctran.c'),
              buildInputs={'configure':command, 'CPPFLAGS':env['CPPFLAGS'], 'LIBS':env['LIBS']},
              logsSha256={name:sha(out/name) for name in ('configure.log','make.log')})
(out/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
