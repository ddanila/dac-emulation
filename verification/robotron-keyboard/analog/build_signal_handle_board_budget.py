#!/usr/bin/env python3
"""Build initialized real-bridge signal-handle bindings and scan measurements."""
import argparse,json,subprocess
from pathlib import Path
import build_callback_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    original=(HERE/'fixtures/callback_board_budget.h').read_text()
    helper=(HERE/'fixtures/signal_handle_board_budget.h').read_text()
    marker='void Robotron_callback_budget(struct ng_vvp*ctx)'
    revised=once(original,marker,helper+'\n'+marker)
    revised=once(revised,'    /* This diagnostic deliberately does not execute the transient campaign. */','    signal_handle_board_budget(ctx);\n    /* This diagnostic deliberately does not execute the transient campaign. */')
    shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),original,revised))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    for source in (Path(__file__).resolve(),HERE/'fixtures/signal_handle_board_budget.h'):r['sources'][str(source)]=sha(source)
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Diagnostic-only initialized bridge signal handles for every port, native node/scope identities and initial full-scan cost, alongside prior callback binding controls. Terminates before the first coroutine advance. Not transient or combined operational qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
