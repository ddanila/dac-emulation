#!/usr/bin/env python3
"""Build isolated callback/payload association runtime and matched display modules."""
import argparse,json,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_queue_observer import COMMIT,ARCHIVE
HERE=Path(__file__).resolve().parent
RUNTIME_PATCHES=('icarus-queue-observer.patch','icarus-sync-observer.patch','icarus-sync-family-observer.patch','icarus-callback-payload-link.patch')
DISPLAY_PATCHES=('icarus-display-observer.patch','icarus-display-payload-link.patch')


def build(archive,out,bison,jobs):
    if jobs<1 or sha(archive)!=ARCHIVE:raise ValueError('Need pinned source archive and positive jobs')
    out=out.resolve();out.mkdir(exist_ok=False);commands=[]
    def run(command,name):
        commands.append(command)
        with (out/(name+'.log')).open('w') as log:subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    run(['tar','-xzf',str(archive.resolve()),'--strip-components=1'],'unpack')
    for name in RUNTIME_PATCHES:run(['patch','-p1','-i',str(HERE/'engine-patches'/name)],name)
    run(['sh','autoconf.sh'],'autoconf')
    run(['./configure','--enable-libvvp','--prefix='+str(out/'install'),'YACC='+str(bison.resolve())],'configure')
    run(['make','version_tag.h','version.exe'],'version')
    run(['make','-C','vvp','-j'+str(jobs)],'runtime-build')
    run(['make','-C','vpi','-j'+str(jobs),'system.vpi'],'baseline-build')
    (out/'baseline').mkdir();shutil.copyfile(out/'vpi/system.vpi',out/'baseline/system.vpi')
    for name in DISPLAY_PATCHES:run(['patch','-p1','-i',str(HERE/'engine-patches'/name)],name)
    (out/'vpi/system.vpi').unlink()
    run(['make','-C','vpi','-j'+str(jobs),'system.vpi'],'display-build')
    for target,names in [('vvp/libvvp.so',('robotron_vvp_sync_payload_identity','robotron_vvp_sync_swap_payloads')),('vpi/system.vpi',('robotron_display_associations','robotron_display_swap_callback_data'))]:
        exported=subprocess.check_output(['nm','-g',str(out/target)],text=True)
        if not all(n in exported for n in names):raise ValueError('Missing association exports')
    sources=[Path(__file__),HERE/'build_private_queue_observer.py',*[HERE/'engine-patches'/n for n in (*RUNTIME_PATCHES,*DISPLAY_PATCHES)]]
    result={'qualified':False,'commit':COMMIT,'archiveSha256':ARCHIVE,'commands':commands,
            'compiler':subprocess.check_output(['c++','--version'],text=True),'sources':{str(p.relative_to(HERE)):sha(p) for p in sources},
            'outputs':{n:sha(out/n) for n in ('vvp/vvp','vvp/libvvp.so','vvp/vpi_callback.cc','baseline/system.vpi','vpi/system.vpi','vpi/sys_display.c')},
            'scope':'Direct live callback handle/function/user-data association to typed display payloads. Intentional payload swap must be restored before scheduler continuation. No general rollback or freed-storage qualification.'}
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
