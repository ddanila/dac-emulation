#!/usr/bin/env python3
"""Build a separate observational bridge from the retained drain candidate."""
import argparse
import json
import platform
import subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent
RETAINED=HERE/'reports/postreset-drain-clamp'

INSERTIONS=[
('''                vpi_put_value(ctx->ports[i].handle, &val, NULL, vpiNoDelay);''',
 '''                fprintf(stderr,"DELIVERY_AUDIT input actual=%.17g target=%.17g base=%.17g stop=%u port=%s aval=%u bval=%u\\n",get_time(ctx),ctx->cosim_context->vtime,ctx->base_time,ctx->stop_cb!=NULL,vpi_get_str(vpiName,ctx->ports[i].handle),(unsigned)val.value.vector->aval,(unsigned)val.value.vector->bval);
''', 'before'),
('''    if (ctx->stop_cb) {''',
 '''    fprintf(stderr,"DELIVERY_AUDIT output-before actual=%.17g target=%.17g base=%.17g stop=%u port=%s aval=%u bval=%u\\n",get_time(ctx),ctx->cosim_context->vtime,ctx->base_time,ctx->stop_cb!=NULL,vpi_get_str(vpiName,cb->obj),(unsigned)cb->value->value.vector->aval,(unsigned)cb->value->value.vector->bval);
''', 'before'),
('''    /* Record the value. */''',
 '''    fprintf(stderr,"DELIVERY_AUDIT output-after actual=%.17g target=%.17g base=%.17g stop=%u port=%s aval=%u bval=%u\\n",get_time(ctx),ctx->cosim_context->vtime,ctx->base_time,ctx->stop_cb!=NULL,vpi_get_str(vpiName,cb->obj),(unsigned)cb->value->value.vector->aval,(unsigned)cb->value->value.vector->bval);
''', 'before')]


def instrument(source):
    for marker,addition,_ in INSERTIONS:
        if source.count(marker)!=1:raise ValueError('Changed delivery audit boundary')
        source=source.replace(marker,addition+marker)
    return source


def build(source,candidate,vpi_header,out):
    source=source.resolve();candidate=candidate.resolve();vpi_header=vpi_header.resolve();out=out.resolve()
    receipt=json.loads((candidate/'build.json').read_text())
    if receipt!=json.loads((RETAINED/'candidate-build.json').read_text()) or any(sha(candidate/n)!=h for n,h in receipt['outputs'].items()):
        raise ValueError('Changed retained drain candidate')
    headers=[source/'src/xspice/verilog/icarus_shim.h',source/'src/xspice/verilog/coroutine_cosim.h',source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h',vpi_header]
    for path in headers:
        expected=[h for n,h in receipt['sources'].items() if Path(n).name==path.name]
        if expected!=[sha(path)]:raise ValueError('Changed candidate header')
    out.mkdir(exist_ok=False)
    (out/'vpi.c').write_text(instrument((candidate/'vpi.c').read_text()))
    flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
    command=['cc','-fPIC','-I'+str(source/'src/include'),'-I'+str(source/'src/xspice/verilog'),'-I'+str(vpi_header.parent),*flags,str(out/'vpi.c'),'-o',str(out/'ivlng.vpi')]
    subprocess.run(command,check=True)
    result=dict(qualified=False,command=command,sources={str(p):sha(p) for p in [Path(__file__),candidate/'build.json',candidate/'vpi.c',*headers]},outputs={n:sha(out/n) for n in ('vpi.c','ivlng.vpi')},scope='Adds input-application and before/after output-callback logging only. Values are the first aval/bval word used by the existing bridge. Input threshold detection is upstream and remains unobserved. Full capture equivalence and convergence remain required.')
    (out/'build.json').write_text(json.dumps(result,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','candidate','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.candidate,a.vpi_header,a.out)
