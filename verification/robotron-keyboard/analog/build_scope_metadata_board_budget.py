#!/usr/bin/env python3
"""Measure scope metadata on the initialized real keyboard bridge."""
import argparse,json,subprocess
from pathlib import Path
import build_signal_scope_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
EXTRA=r'''
    int(*scope_metadata)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_inventory");
    int(*scope_references)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_reference_inventory");
    if(!scope_metadata||!scope_references)exit(2);
    callback_budget_file(ctx,scope_metadata,"metadata-before.txt");
    callback_budget_file(ctx,scope_references,"metadata-references-before.txt");
    f=fopen("metadata-budget.txt","w");if(!f)exit(2);
    scope_scan_measure(f,scope_metadata,"metadata");
    scope_scan_measure(f,scope_references,"references");
    if(fclose(f))exit(2);
    callback_budget_file(ctx,scope_metadata,"metadata-after.txt");
    callback_budget_file(ctx,scope_references,"metadata-references-after.txt");
'''


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),base.EXTRA,base.EXTRA+EXTRA))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Initialized real keyboard bridge scope metadata, identity bindings, complete repeat scans and separate local timings. Ends before coroutine execution; no operational board qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
