#!/usr/bin/env python3
"""Build and verify an isolated, pinned monitor solver. No system installation."""
import argparse
from file_hash import digest
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import shutil
import subprocess
import tarfile
import lab
ROOT=Path(__file__).resolve().parent
ARCHIVE_SHA256='894e649651f1838a14095e5a5439e7d3aa63e87ede14d283173fda4fcdef675f'
SOURCE_URL='https://downloads.sourceforge.net/project/ngspice/ng-spice-rework/47/ngspice-47.tar.gz'
FLAGS=['--enable-xspice','--with-x=no','--with-readline=no','CFLAGS=-O2 -fno-fast-math']




def inputs():
    names=('monitor_runtime.py','file_hash.py','lab.py',
           'runtime/ngspice-47-monitor.patch','runtime/crt_schmitt/cfunc.mod',
           'runtime/crt_schmitt/ifspec.ifs')
    return {name:digest(ROOT/name) for name in names}


def receipt(directory):
    """Called only after an actual build; receipt does not qualify model behavior."""
    directory=Path(directory).resolve();install=directory/'install'
    files=[install/'bin/ngspice',install/'share/ngspice/scripts/spinit',*sorted((install/'lib/ngspice').glob('*.cm'))]
    if len(files)<3 or any(not p.is_file() for p in files):raise ValueError('incomplete installed runtime')
    compiler_command=shlex.split(os.environ.get('CC','cc'))
    cxx_command=shlex.split(os.environ.get('CXX','c++'))
    if not compiler_command or not cxx_command:
        raise ValueError('empty configured compiler command')
    result=dict(format='dac-monitor-runtime-v1',source_url=SOURCE_URL,archive_sha256=ARCHIVE_SHA256,
                install_prefix=str(install),inputs=inputs(),configure_flags=FLAGS,
                compiler_command=compiler_command,
                compiler=subprocess.check_output([*compiler_command,'--version'],text=True),
                cxx_command=cxx_command,
                cxx_compiler=subprocess.check_output([*cxx_command,'--version'],text=True),
                version=subprocess.check_output([str(install/'bin/ngspice'),'--version'],text=True),
                files={str(p.relative_to(directory)):digest(p) for p in files},
                qualification='experimental-instrumented-runtime',full_monitor_qualified=False)
    if 'ngspice-47' not in result['version']:raise ValueError('wrong runtime version')
    (directory/'runtime.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def verify(directory):
    directory=Path(directory).resolve();data=json.loads((directory/'runtime.json').read_text())
    if data.get('format')!='dac-monitor-runtime-v1' or data.get('archive_sha256')!=ARCHIVE_SHA256 or data.get('inputs')!=inputs() or data.get('configure_flags')!=FLAGS:
        raise ValueError('runtime provenance mismatch; rebuild required')
    if data.get('install_prefix')!=str(directory/'install'):
        raise ValueError('runtime moved; rebuild required for embedded code-model paths')
    files=data.get('files',{})
    required={'install/bin/ngspice','install/lib/ngspice/analog.cm','install/share/ngspice/scripts/spinit'}
    if not required<=files.keys():
        raise ValueError('incomplete runtime manifest')
    for name,expected in files.items():
        p=(directory/name).resolve()
        if not p.is_relative_to(directory/'install') or digest(p)!=expected:raise ValueError('runtime file hash mismatch')
    return directory/'install/bin/ngspice',data


def extract_source(source, directory):
    """Extract the pinned source without links or paths outside its root."""
    members = source.getmembers()
    for member in members:
        name = PurePosixPath(member.name)
        if (name.is_absolute() or not name.parts or name.parts[0] != 'ngspice-47'
                or '..' in name.parts or not (member.isfile() or member.isdir())):
            raise ValueError('unsafe ngspice source archive member: '+member.name)
    source.extractall(directory, members=members)


def build(archive,directory,*,jobs=4):
    archive=Path(archive).resolve();directory=Path(directory).resolve()
    if digest(archive)!=ARCHIVE_SHA256:raise ValueError('wrong ngspice source archive')
    if type(jobs) is not int or not 1<=jobs<=32:raise ValueError('invalid build parallelism')
    build_inputs=inputs()
    directory.mkdir(parents=True,exist_ok=False)
    with tarfile.open(archive) as source:extract_source(source,directory)
    source=directory/'ngspice-47'
    # Exact context, no fuzz; changing source revision requires a new pinned build.
    lab.run_command(['patch','--batch','--fuzz=0','-p1','-i',str(ROOT/'runtime/ngspice-47-monitor.patch')],source,directory/'patch.log')
    shutil.copytree(ROOT/'runtime/crt_schmitt',source/'src/xspice/icm/analog/crt_schmitt')
    paths=source/'src/xspice/icm/analog/modpath.lst';paths.write_text(paths.read_text()+'crt_schmitt\n')
    lab.run_command(['./configure','--prefix='+str(directory/'install'),*FLAGS],source,directory/'configure.log',timeout=600)
    lab.run_command(['make',f'-j{jobs}'],source,directory/'build.log',timeout=1800)
    lab.run_command(['make','install'],source,directory/'install.log',timeout=600)
    if inputs()!=build_inputs:raise ValueError('runtime sources changed during build; rebuild required')
    return receipt(directory)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--jobs',type=int,default=4)
    a=p.parse_args();build(a.archive,a.output,jobs=a.jobs);print(a.output/'runtime.json')
