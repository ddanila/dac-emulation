#!/usr/bin/env python3
"""Compare host Estonian input with original-ROM keyboard decoding and glyphs."""
import argparse,csv,hashlib,json,os,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];HERE=Path(__file__).resolve().parent
EXPECTED='7c7d7b7e5c60405e'
def command(cmd,log,cwd=ROOT,env=None):
 r=subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,capture_output=True,text=True,timeout=180)
 log.write_text(r.stdout+r.stderr)
 if r.returncode or 'LUA ERROR' in r.stdout+r.stderr:raise RuntimeError(str(log))
 return r.stdout

def read(path):
 rows=list(csv.reader(path.open()));assert len(rows)==8 and all(r[1]=='1' for r in rows)
 return {'guest_bytes':''.join(r[2] for r in rows),'glyphs':[r[3] for r in rows]}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['roms','source','mame','output']:p.add_argument('--'+n,type=Path,required=True)
 p.add_argument('--rustc',default='rustc');p.add_argument('--emcc',help='also run the firmware probe as WASM under Node');a=p.parse_args()
 for n,v in vars(a).items():
  if isinstance(v,Path):setattr(a,n,v.resolve())
 a.output.mkdir(parents=True,exist_ok=False)
 common=['machines/juku/juku.c','machines/juku/juk_disk.c','machines/juku/juku_fdc.c','third_party/cpu/i8080/i8080.c','common/media/media.c','common/trace/trace.c']
 command(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Imachines/juku','-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace',HERE/'capture.c',*common,'-o',a.output/'native'],a.output/'build.log')
 if a.emcc:
  command([a.emcc,'-O2','-std=c11','-Imachines/juku','-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace',HERE/'capture.c',*common,'-sENVIRONMENT=node','-sNODERAWFS=1','-sALLOW_MEMORY_GROWTH=1','-sSTACK_SIZE=4194304','-o',a.output/'capture.cjs'],a.output/'wasm-build.log')
 command([a.rustc,'--edition=2024','--crate-name','juku','--crate-type','rlib','-O',a.source/'core/src/lib.rs','-o',a.output/'libjuku.rlib'],a.output/'rust.log')
 command([a.rustc,'--edition=2024','-O',HERE/'capture.rs','--extern','juku='+str(a.output/'libjuku.rlib'),'-o',a.output/'sinijarv'],a.output/'adapter.log')
 report={'input':'äõöüÄÕÖÜ','expected_guest_bytes':EXPECTED,'native':{},'wasm':{},'comparison':{},'inputs':{},
         'sinijarv_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),
         'dac_base_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
         'mame_version':subprocess.check_output([a.mame,'-help'],text=True).splitlines()[0]}
 for name,profile in [('ekta24',2),('ekta31',0),('ekta32',4),('ekta35',1),('ekta37',0),('ekta43',5),('jmon33',3)]:
  path=a.roms/(name+'.bin');b=path.read_bytes();report['inputs'][name]=hashlib.sha256(b).hexdigest()
  if name=='ekta43':
   corrected=bytearray(b);corrected[10]=sum(b[11:2048])&255;path=a.output/'ekta43-corrected.bin';path.write_bytes(corrected)
   report['ekta43_checksum_correction']={'offset':10,'before':b[10],'after':corrected[10],'sha256':hashlib.sha256(corrected).hexdigest()}
  out=a.output/(name+'.csv');command([a.output/'native',path,profile],out)
  report['native'][name]=read(out);report['native'][name]['profile']=profile
  if a.emcc:
   out=a.output/(name+'-wasm.csv');command(['node',a.output/'capture.cjs',path,profile],out)
   report['wasm'][name]=read(out)
   assert report['wasm'][name]=={k:v for k,v in report['native'][name].items() if k!='profile'}
  print(name,report['native'][name]['guest_bytes'],flush=True)
 out=a.output/'sinijarv.csv';command([a.output/'sinijarv',a.roms/'ekta37.bin'],out);report['comparison']['sinijarv-physical']=read(out)
 for mode in ['natural','physical']:
  dest=a.output/('mame-'+mode);dest.mkdir();out=dest/'input.csv';env=os.environ.copy()
  env.update(JUKU_INPUT_MODE=mode,JUKU_INPUT_OUTPUT=str(out),SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
  command([a.mame,'juku','-bios','3.43m_37','-rompath',a.roms.parent,'-video','none','-sound','none','-nothrottle','-natural',
           '-seconds_to_run','10','-skip_gameinfo','-noreadconfig','-autoboot_delay','2','-autoboot_script',HERE/'mame.lua'],dest/'run.log',dest,env)
  report['comparison']['mame-'+mode]=read(out)
 (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 # Natural-input failures remain visible; never require MAME to keep failing.
 assert all(r['guest_bytes']==EXPECTED for n,r in report['native'].items() if n!='jmon33')
 for n in ['sinijarv-physical','mame-physical']:
  assert report['comparison'][n]['guest_bytes']==EXPECTED
  assert report['comparison'][n]['glyphs']==report['native']['ekta37']['glyphs']
 print(report['comparison'],flush=True)
if __name__=='__main__':main()
