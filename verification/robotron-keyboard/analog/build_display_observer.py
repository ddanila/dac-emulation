#!/usr/bin/env python3
"""Build matched original and typed-strobe-observer modules from pinned source."""
import argparse,json,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_queue_observer import COMMIT,ARCHIVE
HERE=Path(__file__).resolve().parent
PATCH=HERE/'engine-patches/icarus-display-observer.patch'


def build(archive,out,bison,jobs):
    if jobs<1 or sha(archive)!=ARCHIVE:raise ValueError('Need pinned archive and positive job count')
    out=out.resolve();out.mkdir(exist_ok=False);commands=[]
    def run(command,name):
        commands.append(command)
        with (out/(name+'.log')).open('w') as log:subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    run(['tar','-xzf',str(archive.resolve()),'--strip-components=1'],'unpack')
    upstream=sha(out/'vpi/sys_display.c')
    run(['sh','autoconf.sh'],'autoconf')
    run(['./configure','--enable-libvvp','--prefix='+str(out/'install'),'YACC='+str(bison.resolve())],'configure')
    run(['make','version_tag.h','version.exe'],'version')
    run(['make','-C','vpi','-j'+str(jobs),'system.vpi'],'baseline-build')
    (out/'baseline').mkdir();shutil.copyfile(out/'vpi/system.vpi',out/'baseline/system.vpi')
    run(['patch','-p1','-i',str(PATCH)],'patch')
    # Force relinking even when filesystem/make timestamps share one second.
    (out/'vpi/system.vpi').unlink()
    run(['make','-C','vpi','-j'+str(jobs),'system.vpi'],'observer-build')
    exported=subprocess.check_output(['nm','-g',str(out/'vpi/system.vpi')],text=True)
    if not all(name in exported for name in ('robotron_display_inventory','robotron_display_toggle_destination')) or sha(out/'baseline/system.vpi')==sha(out/'vpi/system.vpi'):
        raise ValueError('Observer module was not relinked/exported')
    (out/'observer-symbols.txt').write_text(exported)
    result={'qualified':False,'commit':COMMIT,'archiveSha256':ARCHIVE,'upstreamDisplaySha256':upstream,'commands':commands,
            'compiler':subprocess.check_output(['cc','--version'],text=True),
            'sources':{str(p.relative_to(HERE)):sha(p) for p in (Path(__file__),HERE/'build_private_queue_observer.py',PATCH)},
            'outputs':{n:sha(out/n) for n in ('baseline/system.vpi','vpi/system.vpi','vpi/sys_display.c','observer-symbols.txt')},
            'scope':'Typed strobe-producer registry, metadata and supported argument values with referent identity checks. Source-version and observer effects need separate matched controls. Descriptor internals, arbitrary VPI objects, monitor callbacks and general rollback remain unqualified.'}
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
