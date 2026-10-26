#!/usr/bin/env python3
"""Build a default-off absolute-tick candidate from the audited board VPI."""
import argparse
import json
import platform
import subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_family_bridge import VPI_SOURCE
HERE=Path(__file__).resolve().parent


def instrument(source, helper):
    marker='static PLI_INT32 next_advance_cb(struct t_cb_data *cb);'
    old='''        ticks = (uint64_t)
            ((ctx->cosim_context->vtime - vl_time)  / ctx->tick_length);'''
    if source.count(marker)!=1 or source.count(old)!=1:
        raise ValueError('Changed pinned conversion boundary')
    replacement='''        if (getenv("ROBOTRON_ABSOLUTE_TICKS")) {
            uint64_t target_ticks, current_ticks;
            struct t_vpi_time now = { .type = vpiSimTime };
            vpi_get_time(NULL, &now);
            current_ticks = ((uint64_t)now.high << 32) + now.low;
            if (robotron_absolute_ticks(ctx->cosim_context->vtime,
                                       ctx->tick_length, &target_ticks)) {
                fprintf(stderr,"Invalid absolute tick conversion\\n");
                exit(2);
            }
            ticks = target_ticks > current_ticks ? target_ticks-current_ticks : 0;
        } else {
'''+old+'''
        }'''
    return source.replace(marker,helper+'\n'+marker).replace(old,replacement)


def build(source, vpi, vpi_header, out):
    source=source.resolve();vpi=vpi.resolve();out=out.resolve();vpi_header=vpi_header.resolve()
    if sha(vpi)!=VPI_SOURCE:raise ValueError('Changed audited VPI source')
    out.mkdir(exist_ok=False)
    helper=HERE/'fixtures/absolute_ticks.h'
    (out/'vpi.c').write_text(instrument(vpi.read_text(),helper.read_text()))
    flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
    command=['cc','-fPIC','-I'+str(source/'src/include'),'-I'+str(source/'src/xspice/verilog'),'-I'+str(vpi_header.parent),*flags,str(out/'vpi.c'),'-o',str(out/'ivlng.vpi')]
    subprocess.run(command,check=True)
    deps=[Path(__file__),helper,vpi,vpi_header,source/'src/xspice/verilog/icarus_shim.h',source/'src/xspice/verilog/coroutine_cosim.h',source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'command':command,'sources':{str(p):sha(p) for p in deps},'outputs':{n:sha(out/n) for n in ('vpi.c','ivlng.vpi')},'scope':'Default-off exact absolute binary64 target/tick quotient. Does not change input thresholds, tick length, input application order or backward-time handling. Board rollback and numerical controls required.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
