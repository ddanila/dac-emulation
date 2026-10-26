#!/usr/bin/env python3
"""Build linked display observer with a reversible single-payload board fault."""
import argparse,json,subprocess
from pathlib import Path
import build_display_association as base
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def build(archive,out,bison,jobs):
    runtime,display=base.RUNTIME_PATCHES,base.DISPLAY_PATCHES
    try:
        base.RUNTIME_PATCHES=runtime+('icarus-single-display-runtime.patch',)
        base.DISPLAY_PATCHES=display+('icarus-single-display-module.patch',)
        base.build(archive,out,bison,jobs)
    finally:
        base.RUNTIME_PATCHES,base.DISPLAY_PATCHES=runtime,display
    for target,symbol in [('vvp/libvvp.so','robotron_vvp_sync_toggle_payload_null'),('vpi/system.vpi','robotron_display_toggle_callback_data')]:
        exports=subprocess.check_output(['nm','-g',str(out/target)],text=True)
        if symbol not in exports:raise ValueError('Missing single-payload fault API')
    path=out/'build.json';receipt=json.loads(path.read_text())
    receipt['sources'][Path(__file__).name]=sha(Path(__file__))
    receipt['scope']='Typed display/callback association runtime with reversible single-payload NULL fault. Restore before executing callbacks. Board controls and general rollback remain separate.'
    path.write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
