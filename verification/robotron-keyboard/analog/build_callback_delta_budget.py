#!/usr/bin/env python3
"""Measure compact full-scan callback lists at the real bridge initialization boundary."""
import argparse,json,subprocess
from pathlib import Path
import build_callback_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def compact_helper(source):
    source=once(source,'    if(!inventory||!admit)exit(2);', '''    int(*reference)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_reference");
    int(*delta)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_list_delta_inventory");
    if(!inventory||!admit||!reference||!delta)exit(2);''')
    source=once(source,'    callback_budget_file(ctx,inventory,"callbacks-before.txt");','''    callback_budget_file(ctx,inventory,"callbacks-before.txt");
    callback_budget_file(ctx,reference,"callback-reference.txt");
    callback_budget_file(ctx,delta,"callback-delta-before.txt");''')
    source=once(source,'if(inventory(f)||fflush(f))exit(2);','if(delta(f)||fflush(f))exit(2);')
    return once(source,'    callback_budget_file(ctx,inventory,"callbacks-after.txt");','''    callback_budget_file(ctx,inventory,"callbacks-after.txt");
    callback_budget_file(ctx,delta,"callback-delta-after.txt");''')


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    original=(HERE/'fixtures/callback_board_budget.h').read_text();shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),original,compact_helper(original)))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Diagnostic-only real bridge startup: initialized callback bindings plus immutable owner reference and exact dense/difference pairs. Measures complete native preflight/encoding scans before first coroutine advance. Not operational capture qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
