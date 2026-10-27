#!/usr/bin/env python3
"""Bind initialized memory names to complete array payloads before HDL advance."""
import argparse,json,subprocess
from pathlib import Path
import build_parameter_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
EXTRA=r'''
    int(*memories)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_memory_metadata_inventory");
    int(*array_payloads)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_array_inventory");
    if(!memories||!array_payloads)exit(2);
    callback_budget_file(ctx,memories,"memories-before.txt");
    callback_budget_file(ctx,array_payloads,"memory-arrays-before.txt");
    f=fopen("memories-budget.txt","w");if(!f)exit(2);
    scope_scan_measure(f,memories,"memories");
    if(fclose(f))exit(2);
    callback_budget_file(ctx,memories,"memories-after.txt");
    callback_budget_file(ctx,array_payloads,"memory-arrays-after.txt");
'''


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),base.EXTRA,base.EXTRA+EXTRA))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Initialized actual keyboard memory names and registered handle/array/owner identities with full-scan timing, plus unchanged dense array payload images. No transient or traversal-safety qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
