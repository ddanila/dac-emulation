#!/usr/bin/env python3
"""Add bounded request/actual-time logging to an existing verified Icarus bridge."""
import argparse,json,math,platform,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--ngspice-source',type=Path,required=True);p.add_argument('--vpi-include',type=Path,required=True);p.add_argument('--start',type=float,required=True);p.add_argument('--end',type=float,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
 if not all(map(math.isfinite,(a.start,a.end))) or not 0<=a.start<a.end:p.error('Invalid audit window')
 r=json.loads(a.base.read_text())
 for lib in r['libraries'].values():
  if sha(Path(lib['path']))!=lib['sha256']:raise ValueError('Bridge library changed')
 source=a.base.parent/'vpi.c';text=source.read_text()
 if r['patchSha256']!=sha(HERE/'icarus-startup.patch'):raise ValueError('Unexpected bridge patch')
 # Reapply the recorded startup patch to independently verify the copied source.
 import tempfile,shutil
 with tempfile.TemporaryDirectory() as tmp:
  candidate=Path(tmp)/'vpi.c';upstream=a.ngspice_source/'src/xspice/verilog/vpi.c'
  if sha(upstream)!=r['upstreamSourceSha256']['vpi.c']:raise ValueError('Unexpected upstream')
  shutil.copyfile(upstream,candidate)
  subprocess.run(['patch',str(candidate),str(HERE/'icarus-startup.patch')],check=True,stdout=subprocess.DEVNULL)
  if sha(candidate)!=sha(source):raise ValueError('Unexpected base bridge source')
 window=f'>{a.start!r} && ctx->cosim_context->vtime<{a.end!r}'
 needle='        vl_time = get_time(ctx);';assert text.count(needle)==1
 text=text.replace(needle,needle+f'\n        if(ctx->cosim_context->vtime{window}) fprintf(stderr,"TIME_AUDIT advance target=%.17g actual=%.17g base=%.17g tick=%.17g pending=%u\\n",ctx->cosim_context->vtime,vl_time,ctx->base_time,ctx->tick_length,ctx->out_pending);')
 needle='    if (ctx->stop_cb) {';assert text.count(needle)==1
 text=text.replace(needle,f'    if(get_time(ctx)>{a.start!r} && get_time(ctx)<{a.end!r}) fprintf(stderr,"TIME_AUDIT output actual=%.17g target=%.17g base=%.17g port=%s\\n",get_time(ctx),ctx->cosim_context->vtime,ctx->base_time,vpi_get_str(vpiName,cb->obj));\n'+needle)
 a.out.mkdir(parents=True,exist_ok=False);(a.out/'vpi.c').write_text(text)
 flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared']
 subprocess.run(['cc','-fPIC','-fvisibility=default','-I'+str(a.base.parent/'include'),'-I'+str(a.ngspice_source/'src/include'),'-I'+str(a.ngspice_source/'src/xspice/verilog'),'-I'+str(a.vpi_include),*flags,str(a.out/'vpi.c'),'-o',str(a.out/'ivlng.vpi')],check=True)
 r['audit']={'windowSeconds':[a.start,a.end],'builderSha256':sha(Path(__file__)),'sourceSha256':sha(a.out/'vpi.c'),'baseBridgeSha256':sha(a.base),'scope':'Logging only; no scheduling or error handling changes'}
 r['libraries']['vpi']={'path':str((a.out/'ivlng.vpi').resolve()),'sha256':sha(a.out/'ivlng.vpi')}
 (a.out/'bridge.json').write_text(json.dumps(r,indent=2)+'\n');print(a.out/'bridge.json')
if __name__=='__main__':main()
