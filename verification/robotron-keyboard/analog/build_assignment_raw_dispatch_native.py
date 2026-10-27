#!/usr/bin/env python3
"""Build native assignment admission controls with scheduler-entry tracking."""
import argparse,json,subprocess
from pathlib import Path
import build_assignment_raw_dispatch_runtime as candidate_builder
from build_private_queue_observer import COMMIT,ARCHIVE
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def build(archive,out,bison,jobs):
    if sha(archive)!=ARCHIVE or jobs<1:raise ValueError('Need pinned archive and positive jobs')
    out=out.resolve();out.mkdir(exist_ok=False)
    fixture=HERE/'fixtures/assignment_raw_native.inc'
    for mode in ('original','candidate'):
        root=out/mode;commands=[]
        def run(cmd,name):
            commands.append(cmd)
            with (root/(name+'.log')).open('w') as log:subprocess.run(cmd,cwd=root,stdout=log,stderr=subprocess.STDOUT,check=True)
        if mode=='candidate':
            candidate_builder.build(archive,root,bison,jobs)
            base=json.loads((root/'build.json').read_text())
            (root/'production-build.json').write_text(json.dumps(base,indent=2)+'\n')
        else:
            root.mkdir()
            run(['tar','-xzf',str(archive.resolve()),'--strip-components=1'],'unpack')
            run(['sh','autoconf.sh'],'autoconf')
            run(['./configure','--enable-libvvp','--prefix='+str(root/'install'),'YACC='+str(bison.resolve())],'configure')
            run(['make','version_tag.h','version.exe'],'version')
            base=dict(commit=COMMIT,archiveSha256=ARCHIVE,sources={},outputs={})
        path=root/'vvp/schedule.cc';before=sha(path);path.write_text(path.read_text()+'\n'+fixture.read_text())
        run(['make','-C','vvp','-j'+str(jobs)],'fixture-build')
        base.update(qualified=False,adapterOnly=True,unadaptedScheduleSha256=before,adapterCommands=commands)
        base['sources'].update({str(p.relative_to(HERE)):sha(p) for p in (fixture,Path(__file__))})
        for name in set(base['outputs'])|{'vvp/schedule.cc','vvp/vvp','vvp/libvvp.so'}:base['outputs'][name]=sha(root/name)
        base['scope']='Shared test-only event factory appended to original or candidate schedule.cc; exact classes, subclasses, native queue insertion, synchronous dispatch and deletion. These adapted libraries are not operational board runtimes.'
        (root/'build.json').write_text(json.dumps(base,indent=2)+'\n')
    print(out)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('archive','out','bison'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
