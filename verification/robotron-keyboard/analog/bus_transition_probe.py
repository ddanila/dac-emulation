#!/usr/bin/env python3
"""Reproduce tolerance screens and recorded-output analog isolation of a bus prefix."""
import argparse,json,math,os,re,shutil,subprocess,time
from pathlib import Path
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify,verify
from ttl7406_probe import sha

CASES={'nominal':(1e-3,1e-6,1e-12,25,''),'tight':(1e-6,1e-9,1e-15,25,''),
 'relative':(1e-6,1e-6,1e-12,25,''),'voltage':(1e-3,1e-9,1e-12,25,''),
 'current':(1e-3,1e-6,1e-15,25,''),'gear':(1e-6,1e-9,1e-15,25,'method=gear maxord=2'),
 'tight-50ns':(1e-6,1e-9,1e-15,50,''),'tight-12ns':(1e-6,1e-9,1e-15,12.5,''),
 'iterations':(1e-6,1e-9,1e-15,25,'itl4=100')}

def settings(deck,case):
 rel,volt,amp,step,extra=CASES[case]
 deck=re.sub(r'^\.options reltol=.*\n','',deck,flags=re.M)
 deck,n=re.subn(r'^\.tran \S+',f'.tran {step:g}n',deck,flags=re.M)
 if n!=1:raise ValueError('Expected one transient')
 return deck.replace('.control',f'.options reltol={rel} vntol={volt} abstol={amp} {extra}\n.control')

def dac_nodes(deck):
 nodes=[]
 for line in deck.splitlines():
  if line.startswith('A') and line.endswith(' drive'):
   groups=re.findall(r'\[([^]]*)\]',line)
   if len(groups)!=2:raise ValueError('Unexpected DAC interface')
   nodes+=groups[1].split()
 if not nodes or len(nodes)!=len(set(nodes)):raise ValueError('Missing or duplicate DAC outputs')
 return nodes

def compress_boundary(path,nodes):
 traces=[[] for _ in nodes];previous=None
 with path.open() as stream:
  header=next(stream).lower().split()
  if header[1:1+len(nodes)]!=[f'v({n.lower()})' for n in nodes]:raise ValueError('Boundary column mismatch')
  for line in stream:
   row=list(map(float,line.split()))
   if len(row)!=len(header) or not all(map(math.isfinite,row)):raise ValueError('Invalid boundary values')
   if previous is not None and row[0]<previous:raise ValueError('Nonmonotonic boundary')
   previous=row[0]
   for j,trace in enumerate(traces):
    point=(row[0],row[j+1])
    # Only remove middle samples on exactly constant plateaus; retain ramps.
    if len(trace)>1 and trace[-2][1]==trace[-1][1]==point[1]:trace[-1]=point
    else:trace.append(point)
 if not traces[0] or traces[0][0][0]!=0:raise ValueError('Boundary must include startup')
 return traces

def replay(deck,nodes,traces):
 lines=[]
 for line in deck.splitlines():
  if line.startswith('A') and line.split()[0] not in {'Abus','Abus_low','Abus_high','Amatrix','Arxdata','Arxclock','Afixture','Ahdl','Adrive','Acolumns'}:raise ValueError('Unclassified analog interface: '+line.split()[0])
  if line.startswith('A') or line.startswith('+ lib_args') or re.match(r'^\.model (hdl|drive|data_receiver|clock_receiver) ',line):continue
  lines.append(line)
 pwls=['Vreplay_'+n+' '+n+' 0 PWL('+' '.join(f'{t:.17g} {v:.17g}' for t,v in points)+')' for n,points in zip(nodes,traces)]
 return '\n'.join(lines).replace('.control','\n'.join(pwls)+'\n.control')

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
 p.add_argument('--ngspice',required=True);p.add_argument('--spinit',type=Path,required=True);p.add_argument('--timeout',type=float,default=45)
 p.add_argument('--mode',choices=('sweep','boundary'),default='sweep');p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES));a=p.parse_args()
 runtime,env=identify(a.ngspice,a.spinit);env['ROBOTRON_EVAL_CACHE']='off';a.out.mkdir(parents=True,exist_ok=False)
 (a.out/'runtime.json').write_text(json.dumps(runtime,indent=2)+'\n');base=(a.prepared/'io.cir').read_text()
 def run(name,deck):
  folder=a.out/name;folder.mkdir()
  for n in ('io.vvp','s600.hex'):
   if (a.prepared/n).exists():shutil.copyfile(a.prepared/n,folder/n)
  (folder/'io.cir').write_text(deck);start=time.monotonic();code=None;timedout=False
  with (folder/'ngspice.log').open('w') as log:
   try:code=subprocess.run([a.ngspice,'-n','-b','io.cir'],cwd=folder,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=a.timeout).returncode
   except subprocess.TimeoutExpired:timedout=True
  verify(runtime);diagnostic=solver_diagnostic((folder/'ngspice.log').read_text())
  result={'exitCode':code,'timedOut':timedout,'elapsedSeconds':time.monotonic()-start,'diagnostic':diagnostic,'qualified':False,'sourceDeckSha256':sha(a.prepared/'io.cir'),'deckSha256':sha(folder/'io.cir')}
  (folder/'run.json').write_text(json.dumps(result,indent=2)+'\n');print(name,result,flush=True)
  return folder,not timedout and code==0 and diagnostic is None
 if a.mode=='sweep':
  for case in a.cases:run(case,settings(base,case))
 else:
  nodes=dac_nodes(base);signals=' '.join('v('+n+')' for n in nodes+['n_D1','n_p5V','n_CABLE_5V'])
  deck=re.sub(r'^\.save .*$', '.save '+signals,base,flags=re.M);deck=re.sub(r'^wrdata .*$', 'wrdata boundary.txt '+signals,deck,flags=re.M)
  folder,ok=run('coupled',settings(deck,'nominal'))
  if not ok:raise ValueError('Cannot replay an incomplete coupled boundary')
  traces=compress_boundary(folder/'boundary.txt',nodes);isolated=replay(deck,nodes,traces)
  for case in a.cases:run('replay-'+case,settings(isolated,case))
if __name__=='__main__':main()
