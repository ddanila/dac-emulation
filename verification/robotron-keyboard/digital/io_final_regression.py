#!/usr/bin/env python3
"""Replay read WAIT and non-I/O controls against the complete I/O candidate."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from io_flags_candidate import replace_once
HERE=Path(__file__).resolve().parent

def main():
 ap=argparse.ArgumentParser();ap.add_argument('kind',choices=['read','nonio']);ap.add_argument('--out',type=Path);a=ap.parse_args()
 out=(a.out or ROOT/('build/keyboard-controller-io-final-'+a.kind)).resolve();out.mkdir(parents=True,exist_ok=True)
 original=HERE/('io_wait_probe.py' if a.kind=='read' else 'io_nonio_probe.py');text=original.read_text()
 text=replace_once(text,'HERE=Path(__file__).resolve().parent',f'HERE=Path({str(HERE)!r})'+'''
from io_complete_candidate import c_half as c_generate,hdl_wrapper as hdl_generate
from io_repeat_candidate import c_core as generate,hdl_core as complete_hdl
''')
 text='import sys\nsys.path.insert(0,'+repr(str(HERE))+')\n'+text
 if a.kind=='read':
  text=replace_once(text,"core if profile=='old' else core_generate(core)","core if profile=='old' else complete_hdl(core)")
 else:
  text=replace_once(text,"core_generate(flags_generate((vendor/'tv80_core.v').read_text()))", "complete_hdl((vendor/'tv80_core.v').read_text())")
 script=out/'producer.py';script.write_text(text)
 subprocess.run(['python3',str(script),'--out',str(out)],check=True)
 path=out/'assessment.json';r=json.loads(path.read_text());r['sources'].pop(str(script.relative_to(ROOT)))
 for p in [Path(__file__),original,HERE/'io_complete_candidate.py',HERE/'io_repeat_candidate.py']:r['sources'][str(p.relative_to(ROOT))]=sha(p)
 r['composedArtifacts']={'producer.py':sha(script)};r['profile']='Complete I/O candidate regression'
 path.write_text(json.dumps(r,indent=2)+'\n')
if __name__=='__main__':main()
