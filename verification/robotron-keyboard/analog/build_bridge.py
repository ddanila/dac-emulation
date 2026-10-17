#!/usr/bin/env python3
"""Build the pinned ngspice/Icarus shim with exported symbols and startup fix."""
import argparse
import hashlib
import json
import platform
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--ngspice-source', type=Path, required=True)
    p.add_argument('--icarus-source', type=Path, required=True)
    p.add_argument('--libvvp', type=Path, required=True)
    p.add_argument('--cc', default='cc')
    p.add_argument('--out', type=Path, default=ROOT / 'build/keyboard-controller-analog/bridge')
    a = p.parse_args()
    source = a.ngspice_source.resolve() / 'src/xspice/verilog'
    icarus = a.icarus_source.resolve()
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / 'bridge.json').unlink(missing_ok=True)
    hashes = {'vpi.c': '4e4fd55d0daa123f5cad0b93f453be29bff530128fcbcca1d686e9ad6f261761',
              'icarus_shim.c': '53d62ad7b82372826a183f2f5ed0d89fbb90845d312ff7f2c2e0b489db668f2b'}
    for name, expected in hashes.items():
        if digest(source / name) != expected:
            raise ValueError('Expected unmodified ngspice 47 source: ' + name)
    commit = subprocess.check_output(['git', '-C', str(icarus), 'rev-parse', 'HEAD'], text=True).strip()
    if commit != 'dfeee909ed9f20b4870dd93423156c0170c0e1ff':
        raise ValueError('Expected Icarus v13_0 source commit')
    if not a.libvvp.is_file():
        raise ValueError('Build Icarus with --enable-libvvp first')
    shutil.copyfile(source / 'vpi.c', out / 'vpi.c')
    subprocess.run(['patch', str(out / 'vpi.c'), str(HERE / 'icarus-startup.patch')], check=True)
    include = out / 'include/ngspice'
    include.mkdir(parents=True, exist_ok=True)
    (include / 'config.h').write_text('/* Standalone shim: runtime paths passed explicitly. */\n')
    common = [a.cc, '-fPIC', '-fvisibility=default', '-I' + str(out / 'include'),
              '-I' + str(a.ngspice_source.resolve() / 'src/include'),
              '-I' + str(source), '-I' + str(icarus)]
    mac = platform.system() == 'Darwin'
    for name, src in [('ivlng.so', source / 'icarus_shim.c'), ('ivlng.vpi', out / 'vpi.c')]:
        flags = (['-dynamiclib' if name.endswith('.so') else '-bundle', '-undefined', 'dynamic_lookup']
                 if mac else ['-shared'])
        subprocess.run(common + flags + [str(src), '-o', str(out / name)], check=True)
    report = {'ngspiceSourceVersion': '47', 'upstreamSourceSha256': hashes,
              'icarusCommit': commit, 'patchSha256': digest(HERE / 'icarus-startup.patch'),
              'compiler': subprocess.check_output([a.cc, '--version'], text=True).splitlines()[0],
              'libraries': {name: {'path': str(path.resolve()), 'sha256': digest(path)}
                            for name, path in [('shim', out / 'ivlng.so'), ('vpi', out / 'ivlng.vpi'),
                                               ('libvvp', a.libvvp)]}}
    (out / 'bridge.json').write_text(json.dumps(report, indent=2) + '\n')
    print(out / 'bridge.json')

if __name__ == '__main__':
    main()
