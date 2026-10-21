#!/usr/bin/env python3
"""Build logging-only capacitor contributions alongside the represented-step linear audit."""
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
parser.add_argument('--audit-window', choices=('minimum-step', 'transition'), default='minimum-step')
parser.add_argument('--assembly-correction', action='store_true')
args = parser.parse_args()
base, out = args.base.resolve(), args.out.resolve()
analog = Path(__file__).resolve().parents[2]
parent = json.loads((base/'provenance.json').read_text())
integration = parent['baseProvenance']
linear = integration['baseProvenance']
for name, digest in linear['equationSourceSha256'].items():
    if name == 'src/maths/ni/niinteg.c':
        digest = integration['integrationSourceSha256']
    if name == 'src/maths/ni/niiter.c':
        digest = parent['auditedLinearSourceSha256']
    if sha(base/'source'/name) != digest:
        raise ValueError('Base source differs: '+name)
for name, digest in [
        ('src/spicelib/analysis/dctran.c', parent['transientSourceSha256']),
        ('src/spicelib/analysis/represented_time_step.h', parent['headerSha256']),
        ('src/maths/ni/mpfr_integration.h', integration['headerSha256']),
        ('src/maths/sparse/mpfr_linear_solver.h', linear['kernelSha256'])]:
    if sha(base/'source'/name) != digest:
        raise ValueError('Base source differs: '+name)
if sha(base/'source/src/spicelib/devices/cap/capload.c') != 'c969db26eef78270ffc78ac2195bfde5724e1a30f82637fa6f7cc482f293675b':
    raise ValueError('Capacitor source differs from audited baseline')
patch = analog/'engine-patches/ngspice-47-capacitor-stamp-audit.patch'
out.mkdir()
shutil.copytree(base/'source', out/'source')
(out/'build').mkdir()
with patch.open() as stream:
    subprocess.run(['patch', '-p1'], cwd=out/'source', stdin=stream, check=True)
window_patch = analog/'engine-patches/ngspice-47-capacitor-window-audit.patch'
if args.audit_window == 'transition':
    with window_patch.open() as stream:
        subprocess.run(['patch', '-p1'], cwd=out/'source', stdin=stream, check=True)
assembly_patch = analog/'engine-patches/ngspice-47-capacitor-assembly.patch'
assembly_header = analog/'engine-patches/capacitor_assembly.h'
if args.assembly_correction:
    shutil.copy2(assembly_header, out/'source/src/maths/sparse/capacitor_assembly.h')
    with assembly_patch.open() as stream:
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
              auditPatchSha256=sha(patch), auditWindow=args.audit_window,
              assemblyPatchSha256=sha(assembly_patch) if args.assembly_correction else None,
              assemblyHeaderSha256=sha(assembly_header) if args.assembly_correction else None,
              auditWindowPatchSha256=sha(window_patch) if args.audit_window == 'transition' else None,
              auditedLinearSourceSha256=sha(out/'source/src/maths/ni/niiter.c'),
              auditedCapacitorSourceSha256=sha(out/'source/src/spicelib/devices/cap/capload.c'),
              executableSha256=sha(out/'build/src/ngspice'),
              buildInputs={'configure': command, 'CPPFLAGS': env['CPPFLAGS'], 'LIBS': env['LIBS']},
              logsSha256={name: sha(out/name) for name in ('configure.log', 'make.log')})
(out/'provenance.json').write_text(json.dumps(report, indent=2)+'\n')
print(out/'build/src/ngspice')
