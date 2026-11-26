#!/usr/bin/env python3
"""Inventory host identities through historical keyboard ROMs; failures are findings."""
import argparse,csv,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
PAIRS=[('ekta24',2),('ekta31',0),('ekta32',4),('ekta35',1),('ekta37',0),('ekta43',5),('jmon33',3)]
def run(cmd):
 return subprocess.check_output(list(map(str,cmd)),cwd=ROOT,text=True,timeout=300)
def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--roms',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--emcc')
 a=p.parse_args();a.output=a.output.resolve();a.roms=a.roms.resolve();a.output.mkdir(parents=True,exist_ok=False)
 sources=['machines/juku/juku.c','machines/juku/juk_disk.c','machines/juku/juku_fdc.c','third_party/cpu/i8080/i8080.c','common/media/media.c','common/trace/trace.c']
 flags=['-O2','-std=c11','-Imachines/juku','-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace']
 for probe in ['capture','hold','physical']:
  run(['cc',*flags,HERE/(probe+'.c'),*sources,'-o',a.output/probe])
  if a.emcc:run([a.emcc,*flags,HERE/(probe+'.c'),*sources,'-sENVIRONMENT=node','-sNODERAWFS=1','-sALLOW_MEMORY_GROWTH=1','-sSTACK_SIZE=4194304','-o',a.output/(probe+'.cjs')])
 report={'source_revision':run(['git','rev-parse','HEAD']).strip(),'profiles':{},'scope':'255 nonzero host identities, fresh monitor TTI calls; hold/release/repress/repeated-down/release at four million cycles each. Raw guest codes, not Unicode glyph claims.'}
 inputs=[*sources,'machines/juku/juku_internal.h','machines/juku/profiles.inc','machines/juku/keyboard.inc',*[str((HERE/(p+'.c')).relative_to(ROOT)) for p in ['capture','hold','physical']]]
 report['source_sha256']={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs}
 report['source_worktree_modified']=bool(run(['git','status','--porcelain']).strip())
 for name,profile in PAIRS:
  rom=a.roms/(name+'.bin');b=rom.read_bytes();entry={'profile':profile,'rom_sha256':hashlib.sha256(b).hexdigest()}
  if name=='ekta43':
   patched=bytearray(b);patched[10]=sum(b[11:2048])&255;rom=a.output/'ekta43.bin';rom.write_bytes(patched)
   entry['checksum_correction']={'offset':10,'before':b[10],'after':patched[10]}
  for probe in ['capture','hold','physical']:
   raw=run([a.output/probe,rom,profile]);(a.output/(name+'-'+probe+'.csv')).write_text(raw)
   rows=list(csv.reader(raw.splitlines()))
   if probe=='capture':
    assert len(rows)==255
    entry['host_to_guest']={r[0]:r[2] if r[1]=='1' else None for r in rows}
    entry['ascii_letters_digits_pass']=all(entry['host_to_guest'][f'{k:02x}']==f'{k:02x}' for k in [*range(48,58),*range(65,91),*range(97,123)])
   elif probe=='hold':entry['hold_counts']=[int(r[1]) for r in rows]
   else:entry['physical']={r[0]:r[2] if r[1]=='1' else None for r in rows}
   if a.emcc:
    wasm=run(['node',a.output/(probe+'.cjs'),rom,profile]);(a.output/(name+'-'+probe+'-wasm.csv')).write_text(wasm)
    assert raw==wasm,(name,probe,'native/WASM disagree')
  # These assertions exercise behavior; the saved report is never a golden file.
  assert entry['ascii_letters_digits_pass']
  assert entry['hold_counts'][0]>1 and entry['hold_counts'][0]==entry['hold_counts'][1]
  assert entry['hold_counts'][3]>entry['hold_counts'][2] and entry['hold_counts'][3]==entry['hold_counts'][4]
  for case,value in [('a','61'),('shift-a','41'),('ctrl-a','01'),('caps-a','41'),('up','0b'),('right','0c'),('F1','13'),('F8','1a'),('keypad-enter','0d')]:
   assert entry['physical'][case]==value,(name,case,entry['physical'][case])
  assert entry['physical']['language-a']==('61' if name=='jmon33' else 'c1')
  if name=='ekta43':
   assert entry['physical']['numlock-pad1']=='31'
   assert entry['physical']['right-ctrl-a']=='01'
  for k in '!\"#$%&()*+,-./:;<=>?_':
   assert entry['host_to_guest'][f'{ord(k):02x}']==f'{ord(k):02x}',(name,k)
  entry['native_wasm_agree']=True if a.emcc else None
  report['profiles'][name]=entry;print(name,entry['ascii_letters_digits_pass'],entry['hold_counts'],flush=True)
 (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
if __name__=='__main__':main()
