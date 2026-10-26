#!/usr/bin/env python3
"""Build an isolated opt-in Icarus callback-family observer from a pinned archive."""
import argparse,json,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
COMMIT='dfeee909ed9f20b4870dd93423156c0170c0e1ff'
ARCHIVE='c3a18398dd25073845550af2f35926193f4d3aa7cd7080122bdc501f59717c00'
SCHEDULE='06a3f5ffa3aa411e5c07473c206a86783a8a18fdea2f666f256efd38bebb23d8'
PATCH=HERE/'engine-patches/icarus-queue-observer.patch'
SYNC_PATCH=HERE/'engine-patches/icarus-sync-observer.patch'
FAMILY_PATCH=HERE/'engine-patches/icarus-sync-family-observer.patch'


def build(archive,out,bison,jobs):
    if jobs<1 or sha(archive)!=ARCHIVE:raise ValueError('Need pinned source archive and positive job count')
    out=out.resolve();out.mkdir(exist_ok=False)
    commands=[]
    def run(command,name):
        commands.append(command)
        with (out/(name+'.log')).open('w') as log:
            subprocess.run(command,cwd=out,stdout=log,stderr=subprocess.STDOUT,check=True)
    run(['tar','-xzf',str(archive.resolve()),'--strip-components=1'],'unpack')
    if sha(out/'vvp/schedule.cc')!=SCHEDULE:raise ValueError('Changed scheduler source')
    run(['patch','-p1','-i',str(PATCH)],'patch')
    run(['patch','-p1','-i',str(SYNC_PATCH)],'sync-patch')
    run(['patch','-p1','-i',str(FAMILY_PATCH)],'family-patch')
    run(['sh','autoconf.sh'],'autoconf')
    run(['./configure','--enable-libvvp','--prefix='+str(out/'install'),'YACC='+str(bison.resolve())],'configure')
    run(['make','version_tag.h','version.exe'],'version')
    run(['make','-C','vvp','-j'+str(jobs)],'build')
    receipt={'qualified':False,'commit':COMMIT,'archiveSha256':ARCHIVE,'upstreamSchedulerSha256':SCHEDULE,
             'sourceUrl':f'https://codeload.github.com/steveicarus/iverilog/tar.gz/{COMMIT}',
             'sources':{str(p.relative_to(HERE)):sha(p) for p in (Path(__file__),PATCH,SYNC_PATCH,FAMILY_PATCH)},
             'commands':commands,'compiler':subprocess.check_output(['c++','--version'],text=True),
             'outputs':{n:sha(out/n) for n in ('vvp/libvvp.so','vvp/vvp','vvp/schedule.cc','vvp/vpi_callback.cc')},
             'scope':'Family-aware synchronization callback fields, registered function module offsets and lifetime IDs. The unsafe v1 API fails closed; index is never serialized and unknown-family optional fields are not read. Registry bookkeeping runs in all candidate modes. Arbitrary referents, executing stack, freed storage and general rollback remain unqualified.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','out','bison'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
