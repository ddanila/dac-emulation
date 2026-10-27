#!/usr/bin/env python3
"""Measure complete compact scans and retain every initialized board record."""
import argparse,json,subprocess
from pathlib import Path
import build_scope_metadata_board_budget as base
from build_startup_callback_bridge import once
from ttl7406_probe import sha
MEASURE=r'''
static void metadata_compact_measure(int(*api)(FILE*),const char*path,FILE*budget,const char*label)
{
    FILE*f=fopen(path,"w");if(!f)exit(2);
    for(unsigned i=0;i<64;++i){
        double start=callback_budget_now();if(api(f)||fflush(f))exit(2);
        double elapsed=callback_budget_now()-start;
        if(fprintf(budget,"COMPACT_SCAN %s %u %.9f\n",label,i,elapsed)<0)exit(2);
    }
    if(fclose(f))exit(2);
}
'''
EXTRA=r'''
    int(*compact_metadata)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_compact_inventory");
    int(*compact_references)(FILE*)=dlsym(ctx->vvp_handle,"robotron_vvp_scope_metadata_reference_compact_inventory");
    if(!compact_metadata||!compact_references)exit(2);
    f=fopen("metadata-compact-budget.txt","w");if(!f)exit(2);
    metadata_compact_measure(compact_metadata,"metadata-compact.txt",f,"metadata");
    metadata_compact_measure(compact_references,"metadata-references-compact.txt",f,"references");
    if(fclose(f))exit(2);
    callback_budget_file(ctx,scope_metadata,"metadata-compact-after.txt");
    callback_budget_file(ctx,scope_references,"metadata-references-compact-after.txt");
'''


def build(source,vpi,vpi_header,out):
    base.build(source,vpi,vpi_header,out)
    shim=out/'icarus_shim.c';text=shim.read_text()
    text=once(text,'static void signal_handle_board_budget(',MEASURE+'\nstatic void signal_handle_board_budget(')
    shim.write_text(once(text,base.EXTRA,base.EXTRA+EXTRA))
    p=out/'build.json';r=json.loads(p.read_text());subprocess.run(r['commands'][0],check=True)
    r['sources'][str(Path(__file__).resolve())]=sha(Path(__file__))
    r['outputs']={n:sha(out/n) for n in r['outputs']}
    r['scope']='Initialized keyboard compact metadata/reference scans, every record retained with per-call timing and post-scan dense images. No coroutine advance, changing-state or peak-memory qualification.'
    p.write_text(json.dumps(r,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
