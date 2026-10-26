#!/usr/bin/env python3
"""Build linked display/stop runtime with an executing generic-wrapper observer."""
import argparse,json,subprocess
from pathlib import Path
import build_display_association as base
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def build(archive,out,bison,jobs):
    runtime,display=base.RUNTIME_PATCHES,base.DISPLAY_PATCHES
    try:
        base.RUNTIME_PATCHES=runtime+('icarus-single-display-runtime.patch','icarus-executing-wrapper-link.patch','icarus-executing-event.patch')
        base.DISPLAY_PATCHES=display+('icarus-single-display-module.patch',)
        base.build(archive,out,bison,jobs)
    finally:
        base.RUNTIME_PATCHES,base.DISPLAY_PATCHES=runtime,display
    for target,symbol in [('vvp/libvvp.so','robotron_vvp_executing_inventory'),('vvp/libvvp.so','robotron_vvp_executing_toggle_delete'),('vvp/libvvp.so','robotron_vvp_sync_executing_wrapper'),('vpi/system.vpi','robotron_display_toggle_callback_data')]:
        exports=subprocess.check_output(['nm','-g',str(out/target)],text=True)
        if symbol not in exports:raise ValueError('Missing executing wrapper API')
    path=out/'build.json';receipt=json.loads(path.read_text())
    receipt['sources'][Path(__file__).name]=sha(Path(__file__))
    receipt['scope']='Typed generic-event continuation frames linked to executing sync callbacks, with reversible deletion-flag mutation. Unknown generic objects fail closed. Board controls, other event families and general rollback remain separate.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
