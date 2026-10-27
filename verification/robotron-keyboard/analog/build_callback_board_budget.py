#!/usr/bin/env python3
"""Build a diagnostic bridge that measures initialized native callback lists."""
import argparse,json,subprocess
from pathlib import Path
import build_raw_assignment_bridge as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    shim=out/'icarus_shim.c';shim.write_text(shim.read_text()+'\n'+(HERE/'fixtures/callback_board_budget.h').read_text())
    path=out/'vpi.c';path.write_text(once(path.read_text(),'    cr_init(&ctx->cr_ctx);','    extern void Robotron_callback_budget(struct ng_vvp*);\n    Robotron_callback_budget(ctx);\n    cr_init(&ctx->cr_ctx);'))
    record=out/'build.json';r=json.loads(record.read_text())
    for cmd in r['commands']:subprocess.run(cmd,check=True)
    for p in (Path(__file__).resolve(),HERE/'fixtures/callback_board_budget.h'):r['sources'][str(p)]=sha(p)
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Diagnostic-only actual bridge startup after port metadata and output values initialize. Refuse before callback admission; bind registered outputs, explicitly admit, measure complete list scans, then terminate before first coroutine advance. Not an operational bridge or transient qualification.'
    record.write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
