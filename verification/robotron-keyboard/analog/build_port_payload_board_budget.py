#!/usr/bin/env python3
"""Scan every initialized keyboard port payload and measure complete scan cost."""
import argparse,json,subprocess
from pathlib import Path
import build_scope_metadata_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
EXTRA=r'''
    int(*port_payload)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_port_payload_inventory");
    if(!port_payload)exit(2);
    callback_budget_file(ctx,port_payload,"port-payload-before.txt");
    f=fopen("port-payload-budget.txt","w");if(!f)exit(2);
    scope_scan_measure(f,port_payload,"ports");
    if(fclose(f))exit(2);
    callback_budget_file(ctx,port_payload,"port-payload-after.txt");
'''


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),base.EXTRA,base.EXTRA+EXTRA))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Complete initialized actual keyboard port/bit payload images and full-scan timing, before coroutine advance. Native metadata/reference/signal and prior diagnostic layers remain. No transient/lifecycle qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
