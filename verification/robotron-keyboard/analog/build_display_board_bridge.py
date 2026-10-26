#!/usr/bin/env python3
"""Build a bridge/VPI pair linking typed display payloads at paused board boundaries."""
import argparse,json,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
from build_private_sync_bridge import instrument,UPSTREAM
HERE=Path(__file__).resolve().parent
VPI_SOURCE='54419fef0ac32cba3dc8e13790baabcede9e2bc9c26f55424d7ff8686f08215e'
from build_private_sync_family_bridge import REGISTER,identity_vpi


def build(source,vpi,vpi_header,out):
    source=source.resolve();vpi=vpi.resolve();vpi_header=vpi_header.resolve();out=out.resolve()
    verilog=source/'src/xspice/verilog';upstream=verilog/'icarus_shim.c'
    if platform.system()=='Windows':raise ValueError('Requires reviewed pthread bridge')
    if sha(upstream)!=UPSTREAM or sha(vpi)!=VPI_SOURCE:raise ValueError('Changed pinned bridge/VPI sources')
    out.mkdir(exist_ok=False);(out/'include/ngspice').mkdir(parents=True)
    (out/'include/ngspice/config.h').write_text('/* Standalone bridge: explicit runtime paths. */\n')
    header=HERE/'fixtures/display_board_bridge.h'
    (out/'icarus_shim.c').write_text(instrument(upstream.read_text(),REGISTER+'\n'+header.read_text()))
    (out/'vpi.c').write_text(identity_vpi(vpi.read_text()))
    includes=['-I'+str(out/'include'),'-I'+str(source/'src/include'),'-I'+str(verilog),'-I'+str(vpi_header.parent)]
    commands=[]
    for src,name in [('icarus_shim.c','ivlng.so'),('vpi.c','ivlng.vpi')]:
        flags=(['-dynamiclib'] if name.endswith('.so') else ['-bundle'])+['-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
        command=['cc','-fPIC','-fvisibility=default',*includes,*flags,str(out/src),'-o',str(out/name)]
        subprocess.run(command,check=True);commands.append(command)
    dependencies=[Path(__file__),HERE/'build_private_sync_bridge.py',HERE/'build_private_sync_family_bridge.py',header,upstream,vpi,vpi_header,
                  verilog/'icarus_shim.h',verilog/'coroutine_shim.h',verilog/'coroutine_cosim.h',
                  source/'src/include/ngspice/cmtypes.h',source/'src/include/ngspice/cosim.h']
    receipt={'qualified':False,'commands':commands,'sources':{str(p):sha(p) for p in dependencies},
             'outputs':{n:sha(out/n) for n in ('icarus_shim.c','vpi.c','ivlng.so','ivlng.vpi')},
             'scope':'Single-instance typed display/callback association at paused board boundaries; explicit stop identity and loaded module API. Requires matched controls; other referents, initial callbacks, executing wrappers and general rollback remain open.'}
    (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n');print(out/'build.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','vpi','vpi-header','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.source,a.vpi,a.vpi_header,a.out)
