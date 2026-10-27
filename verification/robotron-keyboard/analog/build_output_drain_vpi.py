#!/usr/bin/env python3
"""Build opt-in same-tick read/write draining before a timed shim return."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def instrument(text):
    declaration='static PLI_INT32 next_advance_cb(struct t_cb_data *cb);'
    branch='''    now.low = (unsigned int)length;
    now.high = (unsigned int)(length >> 32);'''
    marker='''/* Timed callback at end of simulation advance: wait for a command'''
    for token in (declaration,branch,marker):
        if text.count(token)!=1:raise ValueError('Changed stop-callback boundary')
    text=text.replace(declaration,declaration+'\nstatic PLI_INT32 robotron_drain_tick_cb(struct t_cb_data *cb);')
    text=text.replace(branch,branch+'''
    cbd.cb_rtn = length && getenv("ROBOTRON_DRAIN_TICK")
        ? robotron_drain_tick_cb : next_advance_cb;''')
    helper='''/* A timed callback can run before other active/NBA work at this tick.
 * Defer yielding to the read/write synchronization phase. Keep the live
 * handle cancellable by output_cb, which gathers output changes as before. */
static PLI_INT32 robotron_drain_tick_cb(struct t_cb_data *cb)
{
    struct ng_vvp *ctx = (struct ng_vvp *)cb->user_data;
    ctx->stop_cb = set_stop(0, ctx);
    return 0;
}

'''
    return text.replace(marker,helper+marker)


def build(source,candidate,vpi_header,out):
    source=source.resolve();candidate=candidate.resolve();vpi_header=vpi_header.resolve();out=out.resolve()
    baseline=json.loads((HERE/'reports/postreset-tick/coarse/candidate-build.json').read_text());actual=json.loads((candidate/'build.json').read_text())
    if actual!=baseline or any(sha(candidate/n)!=h for n,h in actual['outputs'].items()):raise ValueError('Changed reviewed absolute-tick candidate')
    out.mkdir(exist_ok=False);(out/'vpi.c').write_text(instrument((candidate/'vpi.c').read_text()))
    flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
    cmd=['cc','-fPIC','-I'+str(source/'src/include'),'-I'+str(source/'src/xspice/verilog'),'-I'+str(vpi_header.parent),*flags,str(out/'vpi.c'),'-o',str(out/'ivlng.vpi')]
    subprocess.run(cmd,check=True)
    deps=[Path(__file__),candidate/'build.json',candidate/'vpi.c',vpi_header,source/'src/xspice/verilog/icarus_shim.h',source/'src/xspice/verilog/coroutine_cosim.h',source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt=dict(qualified=False,command=cmd,sources={str(p):sha(p) for p in deps},outputs={n:sha(out/n) for n in ('vpi.c','ivlng.vpi')},scope='Default-off timed-stop deferral to cbReadWriteSynch. Original output-time entry clamp and input application order preserved. Native and board controls required; does not establish full scheduler quiescence or general rollback.')
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','candidate','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.candidate,a.vpi_header,a.out)
