#!/usr/bin/env python3
"""Run combined read/write WAIT and repeated-I/O flags with existing fixtures."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from io_boundary_suite import composed
from io_flags_candidate import replace_once
HERE=Path(__file__).resolve().parent

def producer(kind):
 original,text=composed(kind)
 anchor='from io_wait_candidate import c_generate as wait_c, hdl_generate as wait_hdl, core_generate as wait_core'
 text=replace_once(text,anchor,anchor+'''
from io_complete_candidate import c_half as wait_c, hdl_wrapper as wait_hdl
from io_repeat_candidate import c_core as generate, hdl_core as final_hdl
''')
 text=replace_once(text,"wait_core(flags_generate((ROOT/'third_party/cpu/tv80/tv80_core.v').read_text()))", "final_hdl((ROOT/'third_party/cpu/tv80/tv80_core.v').read_text())")
 if kind=='firmware':
  text=replace_once(text," copies=shadow(root);rom=a.rom.resolve()", " copies=shadow(root);rom=a.rom.resolve()") if " copies=shadow(root);rom=a.rom.resolve()" in text else text
  text=replace_once(text," # An experimental full-tick caller", " (root/'third_party/cpu/chips/z80.h').write_text(generate((ROOT/'third_party/cpu/chips/z80.h').read_text()))\n # An experimental full-tick caller")
 return original,text

def main():
 ap=argparse.ArgumentParser();ap.add_argument('kind',choices=['instructions','firmware']);ap.add_argument('--rom',type=Path);ap.add_argument('--out',type=Path);ap.add_argument('--jobs',type=int,default=3);a=ap.parse_args()
 out=(a.out or ROOT/('build/keyboard-controller-io-final-'+a.kind)).resolve();out.mkdir(parents=True,exist_ok=True)
 original,text=producer(a.kind);script=out/'producer.py';script.write_text(text)
 cmd=['python3',str(script),'--out',str(out)]
 if a.kind=='firmware':
  if not a.rom:ap.error('--rom required')
  cmd+=['--rom',str(a.rom.resolve()),'--jobs',str(a.jobs)]
 subprocess.run(cmd,check=True)
 path=out/'assessment.json';r=json.loads(path.read_text())
 for p in [script,out/'tv80_core.v',out/'tv80_io_candidate.v']:r['sources'].pop(str(p.relative_to(ROOT)),None)
 for p in [Path(__file__),original,HERE/'io_boundary_suite.py',HERE/'io_complete_candidate.py',HERE/'io_repeat_candidate.py',HERE/'io_wait_candidate.py',HERE/'io_flags_candidate.py']:r['sources'][str(p.relative_to(ROOT))]=sha(p)
 r['composedArtifacts']={p.name:sha(p) for p in [script,out/'tv80_core.v',out/'tv80_io_candidate.v']}
 r['profile']='Read/write falling-edge WAIT and repeated-I/O flag candidate';r['qualified']=False
 path.write_text(json.dumps(r,indent=2)+'\n')
 if a.kind=='instructions':
  if not r['allLateCasesAgree']:raise SystemExit('Late instruction mismatch')
 elif not all(r[k] for k in ('functionalAgreement','serialCycleAgreement','realLedTransitionAgreement')):raise SystemExit('Firmware mismatch')
if __name__=='__main__':main()
