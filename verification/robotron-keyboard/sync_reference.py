#!/usr/bin/env python3
"""Pin a clean CAD checkout's checked schematic export, then regenerate HDL."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('cad',type=Path);a=p.parse_args();cad=a.cad.resolve();root=Path(__file__).resolve().parent
if subprocess.check_output(['git','-C',str(cad),'status','--porcelain'],text=True).strip():raise SystemExit('Commit the CAD source before pinning it')
board=cad/'models/robotron-1715m/keyboard-controller'
subprocess.run([sys.executable,board/'tools/export.py','--check'],check=True)
blob=(board/'generated/connectivity.json').read_bytes();revision=subprocess.check_output(['git','-C',str(cad),'rev-parse','HEAD'],text=True).strip()
(root/'reference/connectivity.json').write_bytes(blob)
(root/'reference/source.json').write_text(json.dumps({'repository':'https://github.com/ddanila/3d-models','revision':revision,'path':'models/robotron-1715m/keyboard-controller/generated/connectivity.json','sha256':hashlib.sha256(blob).hexdigest(),'scope':'Reference schematic transcription; physical PCB not yet routed or qualified'},indent=2)+'\n')
subprocess.run([sys.executable,root/'generate.py'],check=True)
print('Pinned CAD connectivity at',revision,'; rerun qualification before publishing results')
