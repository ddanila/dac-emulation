#!/usr/bin/env python3
"""Real ROM qualification through public profile/key APIs, no firmware patches."""
import argparse, csv, hashlib, importlib.util, json, os, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('variants',ROOT/'verification/juku-fdc-variants/run.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
def main():
 p=argparse.ArgumentParser();p.add_argument('--roms',type=Path,required=True);p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output=a.output.resolve();a.roms=a.roms.resolve();a.output.mkdir(parents=True,exist_ok=False)
 v.guest.prepare(a.base,a.output/'files.juk');v.fixture(a.output/'bootstrap.juk')
 report={'inputs':{'base':v.sha(a.base)},'cases':{},'qualification':{},'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()}
 common=['machines/juku/juku.c','machines/juku/juk_disk.c','machines/juku/juku_fdc.c','third_party/cpu/i8080/i8080.c','common/media/media.c','common/trace/trace.c']
 for paced in [0,1]:
  exe=a.output/('paced' if paced else 'native')
  v.command(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Imachines/juku','-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace',f'-DDAC_JUKU_EXPERIMENTAL_FDC_SYNC={paced}','verification/juku-fdc-variants/capture.c',*common,'-o',exe],ROOT,a.output/(exe.name+'-build.log'))
  for rom,profile in [('ekta24',2),('ekta31',0),('ekta35',1),('ekta37',0),('ekta32',4),('ekta43',5),('jmon33',3)]:
   dest=a.output/(rom+'-'+exe.name);dest.mkdir();key=dest/'input.keys'
   rows=[]
   for t,word in [(2000,'T' if rom=='ekta35' else 'TDD'),(16000,'' if rom=='jmon33' else 'fdc25\r')]:
    for i,c in enumerate(word):
     start=t+i*(600 if t==2000 else 280);hold=120
     rows += [f'{start} {ord(c):02x} 1\n',f'{start+hold} 00 0\n']
   key.write_text(''.join(rows));disk=a.output/('bootstrap.juk' if rom=='jmon33' else 'files.juk');end=30000 if rom=='jmon33' else 90000
   env=os.environ.copy();env.pop('JUKU_FDC_BUS_INVERT',None);env['JUKU_PROFILE']=str(profile)
   run=v.command([exe,a.roms/(rom+'.bin'),disk,dest/'capture',key,end,end-1000],ROOT,dest/'run.log',env)
   result=v.inspect_native(dest,disk,rom=='jmon33');result['profile']=profile;result['paced']=bool(paced)
   result['rom_sha256']=v.sha(a.roms/(rom+'.bin'));result['raw_sha256']={f.name:v.sha(f) for f in dest.glob('capture.*') if f.is_file()}
   if rom=='ekta43':
    result['limitation']='Unmodified ROM retries startup; stored block-1 checksum differs from the computed sum. No firmware repair applied.'
    b=(a.roms/(rom+'.bin')).read_bytes();result['checksum']={'stored':b[10],'calculated':sum(b[11:2048])&255}
   elif rom!='jmon33':assert result['file_io']['guest_passed'],dest
   report['cases'][dest.name]=result
   print(dest.name,'bootstrap PASS' if rom=='jmon33' else result['file_io'],flush=True)
   (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
 report['qualification']={'mainboard-juku':'historical EKDOS file I/O verified','mainboard-juss':'historical EKDOS file I/O verified','early-juss':'historical EKDOS file I/O verified','early-juku':'generated bootstrap verified','card-juku':'historical EKDOS file I/O verified; wiring inferred from firmware','card-at':'adapter diagnostics only; historical ROM checksum blocks startup','single-density':'FM/IMD controller diagnostics; historical pairing unverified'}
 (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
