#!/usr/bin/env python3
"""Build typed queued inverter and fixed part-select payload observation."""
import argparse
import json
from pathlib import Path
import subprocess
import build_display_association as base
from ttl7406_probe import sha


def build(archive,out,bison,jobs):
    runtime,display=base.RUNTIME_PATCHES,base.DISPLAY_PATCHES
    try:
        base.RUNTIME_PATCHES=runtime+('icarus-single-display-runtime.patch','icarus-executing-wrapper-link.patch',
                                     'icarus-executing-event.patch','icarus-value-callback-observer.patch','icarus-startup-callback-observer.patch','icarus-assignment-observer.patch','icarus-primitive-observer.patch')
        base.DISPLAY_PATCHES=display+('icarus-single-display-module.patch',)
        base.build(archive,out,bison,jobs)
    finally:
        base.RUNTIME_PATCHES,base.DISPLAY_PATCHES=runtime,display
    exports=subprocess.check_output(['nm','-g',str(out/'vvp/libvvp.so')],text=True)
    for symbol in ('robotron_vvp_primitive_inventory','robotron_vvp_primitive_toggle'):
        if symbol not in exports:raise ValueError('Missing primitive API')
    path=out/'build.json';r=json.loads(path.read_text())
    r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['outputs'].update({n:sha(out/n) for n in ('vvp/vpi_priv.h','vvp/vvp_vpi_callback.h')})
    for name in ('schedule.cc','schedule.h','logic.cc','logic.h','part.cc','part.h'):r['outputs']['vvp/'+name]=sha(out/'vvp'/name)
    r['scope']='Typed queued inverter and static part-select cached vectors, pending destination pointers and slice bounds, with primitive and wrapper lifetimes. Constructors register opaque identities only; payloads are read when queued. Requires controls; island/thread state, destination referents and general rollback remain open.'
    path.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2)
    a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
