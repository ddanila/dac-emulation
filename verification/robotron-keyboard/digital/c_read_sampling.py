#!/usr/bin/env python3
"""Compare T3 late-data witnesses, with an I/O-only falling-edge candidate."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,BOARD,sha
from c_read_candidate import generate
HERE=Path(__file__).resolve().parent

def main():
 p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-c-read-sampling');a=p.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 (out/'candidate.h').write_text(generate((ROOT/'third_party/cpu/chips/z80.h').read_text()))
 def run(args,log=None):
  if log:
   with (out/log).open('w') as f:subprocess.run(list(map(str,args)),stdout=f,check=True,timeout=30)
  else:subprocess.run(list(map(str,args)),check=True,timeout=30)
 run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',out,'-I',HERE,HERE/'c_read_half_test.c','-o',out/'probe'])
 run([out/'probe'],'c.txt')
 # Reuse the independently retained dynamic-input fixture: change data after
 # T3 rising, before falling; check the value the executed OUT instruction sees.
 original=(BOARD/'analog/cpu_read_phase_probe.v').read_text()
 bench=original.replace('tv80n cpu(', 'tv80_io_candidate cpu(')
 bench=bench.replace("assign di=address==0 ? 8'h3e : address==1 ? (late ? 8'h34 : 8'h12) :", "assign di=!iorq_n ? (late ? 8'h34 : 8'h12) : address==0 ? 8'hdb : address==1 ? 8'h80 :")
 bench=bench.replace('!mreq_n && !rd_n && address==1','!iorq_n && !rd_n')
 bench=bench.replace('reset_n && cpu.tstate[2]','reset_n && cpu.i_tv80_core.Auto_Wait_t1 && cpu.tstate[2]')
 for signal in ('tstate','mcycle','i_tv80_core','di_reg'):bench=bench.replace('cpu.'+signal,'cpu.base.'+signal)
 (out/'early.v').write_text(bench)
 (out/'falling.v').write_text(bench.replace("dout!==8'h12","dout!==8'h34"))
 vendor=ROOT/'third_party/cpu/tv80';sources=sorted(vendor.glob('*.v'))
 text=(vendor/'tv80n.v').read_text()
 text=text.replace('  always @(posedge clk)\n','''  reg delayed_io_read=0;
  always @(posedge clk)
    if (!reset_n) delayed_io_read <= 0;
    else delayed_io_read <= iorq && !write && tstate[2] && wait_n;
  always @(posedge clk or negedge clk)
''')
 text=text.replace("if (tstate[2] && wait_n == 1'b1)","if ((clk && !iorq && tstate[2] && wait_n) || (!clk && delayed_io_read))")
 (out/'tv80n_falling.v').write_text(text)
 for name in ('early','falling'):
  rtl=sources if name=='early' else [p for p in sources if p.name!='tv80n.v']+[out/'tv80n_falling.v']
  run(['iverilog','-g2012','-s','probe','-o',out/(name+'.vvp'),*rtl,HERE/'tv80_io_candidate.v',out/(name+'.v')])
  run(['vvp',out/(name+'.vvp')],name+'.txt')
 report={'qualified':False,'cHalfCycleLateDataPassed':True,'hdlLateDataPassed':True,'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'c_read_candidate.py',HERE/'c_read_half.h',HERE/'c_read_half_test.c',HERE/'tv80_io_candidate.v',BOARD/'analog/cpu_read_phase_probe.v',ROOT/'third_party/cpu/chips/z80.h',*sources]},'artifacts':{p.name:sha(p) for p in sorted(out.iterdir()) if p.suffix in ('.h','.v','.txt')},'boundary':'I/O-only half-cycle candidates. C defers the consuming microstate to falling; HDL defers its I/O input latch. Memory/indexed-opcode sampling retains existing behavior. Whole-cycle APIs cannot expose asynchronous inputs between the two calls.'}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n')
 print('C and HDL I/O falling-edge late-data witnesses passed; whole-cycle negative control remains early.')
if __name__=='__main__':main()
