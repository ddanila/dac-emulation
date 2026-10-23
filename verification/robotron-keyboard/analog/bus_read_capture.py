#!/usr/bin/env python3
"""Capture the failing D1 read from a prepared service deck, with bounded runtime."""
import argparse,json,os,re,shutil,subprocess,time
from pathlib import Path
from ttl7406_probe import sha
from failure_evidence import solver_diagnostic

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--ngspice',required=True);p.add_argument('--spinit',required=True);p.add_argument('--timeout',type=float,default=90);a=p.parse_args()
 base=(a.prepared/'io.cir').read_text();signals='v(n_D1) v(n_p5V) '+' '.join(f'v(bus_{s}_{i})' for i in (1,9,17) for s in ('low','high'))
 base=re.sub(r'^\.save .*\n','',base,flags=re.M);base=re.sub(r'^wrdata .*\n','',base,flags=re.M)
 base=base.replace('.control','.save '+signals+'\n.control').replace('quit','wrdata witness.txt '+signals+'\nquit')
 base,count=re.subn(r'^\.tran .*$', '.tran STEPn 1160000n',base,flags=re.M)
 if count!=1:raise ValueError('Expected one service transient')
 a.out.mkdir(parents=True,exist_ok=False)
 for name,step,rel,vntol,abstol in [('default',50,1e-3,1e-6,1e-12),('tight',25,1e-6,1e-9,1e-15),('tighter',12.5,1e-9,1e-12,1e-18)]:
  folder=a.out/name;folder.mkdir()
  for n in ('io.vvp','s600.hex'):shutil.copyfile(a.prepared/n,folder/n)
  deck=base.replace('STEP',str(step)).replace('.control',f'.options reltol={rel} vntol={vntol} abstol={abstol}\n.control');(folder/'io.cir').write_text(deck)
  start=time.monotonic();timedout=False;code=None
  with (folder/'ngspice.log').open('w') as log:
   try:code=subprocess.run([a.ngspice,'-n','-b','io.cir'],cwd=folder,env=dict(os.environ,SPICE_SCRIPTS=a.spinit),stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout).returncode
   except subprocess.TimeoutExpired:timedout=True
  diagnostic=solver_diagnostic((folder/'ngspice.log').read_text())
  result={'sourceDeckSha256':sha(a.prepared/'io.cir'),'executableSha256':sha(Path(a.ngspice)),'deckSha256':sha(folder/'io.cir'),'case':name,'timeoutSeconds':a.timeout,'timedOut':timedout,'exitCode':code,'elapsedSeconds':time.monotonic()-start,'diagnostic':diagnostic,'qualified':False}
  (folder/'run.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
if __name__=='__main__':main()
