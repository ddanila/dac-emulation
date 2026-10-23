#!/usr/bin/env python3
"""Add read-only HDL intent and analog D0 observations to a prepared live fixture."""
import argparse,hashlib,json,shutil,subprocess
from pathlib import Path

SIGNALS=['v(n_D0)','v(data_intent)','v(clock_intent)','v(n_TA_DATEN)','v(n_TA_TAKT)']
MONITOR='''
 // Observe settled combinational intent, preserving X and absolute picoseconds.
 real boundary_stamp;
 wire boundary_d0=bus_sense[0];
 always @(data_sink or clock_sink or bus_sense or wr_n) begin
  boundary_stamp=$realtime*1000.0;
  $strobe("BOUNDARY_PS %0.0f %b %b %b %b %04x %b %b",boundary_stamp,
          boundary_d0,data_sink,clock_sink,wr_n,address,bus_low,bus_high);
 end
'''

def instrument(source):
 anchor=' assign data_sink=(ta_daten'
 if source.count(anchor)!=1:raise ValueError('Expected one electrical output mapping')
 return source.replace(anchor,MONITOR+anchor,1)

def prepare(source,out):
 out.mkdir(parents=True,exist_ok=False)
 for name in ('s600.hex','io.cir'):shutil.copyfile(source/name,out/name)
 hdl=out/'controller_analog.v';hdl.write_text(instrument((source/hdl.name).read_text()))
 receipt=json.loads((source/'build.json').read_text());command=receipt['command'][:]
 command[command.index('-o')+1]=str(out/'io.vvp')
 command=[str(hdl) if x.endswith('.v') and Path(x).resolve()==(source/hdl.name).resolve() else x for x in command]
 if str(hdl) not in command:raise ValueError('Prepared build source not identified')
 subprocess.run(command,check=True)
 deck=(out/'io.cir').read_text();lines=deck.splitlines()
 if sum(x.startswith('.save ') for x in lines)!=1 or sum(x.startswith('wrdata witness.txt ') for x in lines)!=1:raise ValueError('Expected one observer')
 lines=[x+' '+' '.join(SIGNALS) if x.startswith('.save ') else x for x in lines]
 lines=[x+'\nwrdata boundary_witness.txt '+' '.join(SIGNALS) if x.startswith('wrdata witness.txt ') else x for x in lines]
 (out/'io.cir').write_text('\n'.join(lines)+'\n')
 receipt={'command':command,'parent':str(source),'sources':{x:hashlib.sha256(Path(x).read_bytes()).hexdigest() for x in command if x.endswith('.v')},'observerOnly':True}
 (out/'build.json').write_text(json.dumps(receipt,indent=2)+'\n')
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('out',type=Path);a=p.parse_args();prepare(a.source,a.out)
