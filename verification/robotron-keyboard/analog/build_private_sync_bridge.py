#!/usr/bin/env python3
"""Observe live synchronization callbacks at the pthread bridge's HDL step boundaries."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
UPSTREAM='53d62ad7b82372826a183f2f5ed0d89fbb90845d312ff7f2c2e0b489db668f2b'


def instrument(text,header):
    marker='static void step(struct co_info *pinfo)\n{'
    boundary='    cr_yield_to_sim(&ctx->cr_ctx);\n\n    /* Check for output. */'
    if text.count(marker)!=1 or text.count(boundary)!=1:raise ValueError('Changed bridge step boundary')
    text=text.replace(marker,header+'\n'+marker)
    return text.replace(boundary,'    private_sync_boundary(pinfo, "before-step");\n    cr_yield_to_sim(&ctx->cr_ctx);\n    private_sync_boundary(pinfo, "after-step");\n\n    /* Check for output. */')


def build(source,out):
    source=source.resolve();out=out.resolve();verilog=source/'src/xspice/verilog'
    if platform.system()=='Windows':raise ValueError('This observer requires the reviewed pthread bridge')
    upstream=verilog/'icarus_shim.c'
    if sha(upstream)!=UPSTREAM:raise ValueError('Need unmodified ngspice-47 shim')
    out.mkdir(exist_ok=False);(out/'include/ngspice').mkdir(parents=True)
    (out/'include/ngspice/config.h').write_text('/* Standalone bridge: explicit runtime paths. */\n')
    header=HERE/'fixtures/private_sync_bridge.h'
    (out/'icarus_shim.c').write_text(instrument(upstream.read_text(),header.read_text()))
    flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
    command=['cc','-fPIC','-fvisibility=default','-I'+str(out/'include'),'-I'+str(source/'src/include'),'-I'+str(verilog),*flags,str(out/'icarus_shim.c'),'-o',str(out/'ivlng.so')]
    subprocess.run(command,check=True)
    dependencies=[upstream,verilog/'icarus_shim.h',verilog/'coroutine_shim.h',source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'command':command,'sources':{str(p):sha(p) for p in [Path(__file__),header,*dependencies]},
             'outputs':{n:sha(out/n) for n in ('icarus_shim.c','ivlng.so')},
             'scope':'Single-Icarus pthread bridge. Observe before releasing the coroutine mutex in step and after reacquiring it; not during HDL execution. Callback headers and executing sync-callback identity only; function identity, referenced data, the initial start callback and executing stack remain uncovered.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','out'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.source,a.out)
