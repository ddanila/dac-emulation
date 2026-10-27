#!/usr/bin/env python3
"""Measure reference and optimized full inventories on one initialized board."""
import argparse,json,subprocess
from pathlib import Path
import build_callback_signal_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
MEASURE=r'''
static void scope_scan_measure(FILE*out,int(*api)(FILE*),const char*label)
{
    FILE*f=fopen("/dev/null","w");if(!f)exit(2);double sum=0,minimum=1e99,maximum=0;
    for(unsigned i=0;i<64;++i){
        double start=callback_budget_now();if(api(f)||fflush(f))exit(2);
        double elapsed=callback_budget_now()-start;sum+=elapsed;
        if(elapsed<minimum)minimum=elapsed;if(elapsed>maximum)maximum=elapsed;
    }
    if(fclose(f)||fprintf(out,"SCOPE_SCAN %s 64 %.9f %.9f %.9f\n",label,sum,minimum,maximum)<0)exit(2);
}
'''
EXTRA=r'''
    int(*reference_handles)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_signal_handle_reference_inventory");
    int(*reference_links)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_callback_signal_reference_inventory");
    if(!reference_handles||!reference_links)exit(2);
    callback_budget_file(ctx,reference_handles,"handles-reference-before.txt");
    callback_budget_file(ctx,reference_links,"links-reference-before.txt");
    f=fopen("scope-scan-budget.txt","w");if(!f)exit(2);
    scope_scan_measure(f,inventory,"handles-fast");
    scope_scan_measure(f,reference_handles,"handles-reference");
    scope_scan_measure(f,reference_links,"links-reference");
    if(fclose(f))exit(2);
    callback_budget_file(ctx,reference_handles,"handles-reference-after.txt");
    callback_budget_file(ctx,reference_links,"links-reference-after.txt");
'''


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    original=base.linked_helper((HERE/'fixtures/signal_handle_board_budget.h').read_text())
    end=original.rindex('\n}');replacement=MEASURE+'\n'+original[:end]+EXTRA+original[end:]
    shim=out/'icarus_shim.c';shim.write_text(once(shim.read_text(),original,replacement))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Initialized actual bridge reference/optimized signal and callback-link inventories with full scope preflight, exact images and separate scan timings. Ends before coroutine execution; no transient qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
