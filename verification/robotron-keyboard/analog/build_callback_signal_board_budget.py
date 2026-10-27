#!/usr/bin/env python3
"""Measure callback-owner linkage at the initialized keyboard bridge boundary."""
import argparse,json,subprocess
from pathlib import Path
import build_signal_handle_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def linked_helper(source):
    source=once(source,'    if(!admit||!inventory||!graph||!scopes)exit(2);','''    int(*links)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_signal_inventory");
    if(!admit||!inventory||!graph||!scopes||!links)exit(2);''')
    source=once(source,'    callback_budget_file(ctx,inventory,"handles-before.txt");','''    callback_budget_file(ctx,inventory,"handles-before.txt");
    callback_budget_file(ctx,links,"links-before.txt");''')
    source=once(source,'if(inventory(f)||fflush(f))exit(2);','if(links(f)||fflush(f))exit(2);')
    source=once(source,'    callback_budget_file(ctx,inventory,"handles-after.txt");','''    callback_budget_file(ctx,inventory,"handles-after.txt");
    callback_budget_file(ctx,links,"links-after.txt");''')
    # Keep the existing file name for the inherited binding reviewer. The
    # consumer explicitly labels this as combined preflight/link scan cost.
    return source


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    helper=(HERE/'fixtures/signal_handle_board_budget.h').read_text();shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),helper,linked_helper(helper)))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Initialized bridge callback-to-signal/node/filter linkage with full native list/signal preflight and initial encoding cost. The handle-budget timing file measures linkage including both preflights. Ends before coroutine advancement; operational qualification remains separate.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
