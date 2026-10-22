#!/usr/bin/env python3
"""Write WAIT/release oracle for immediate, ED and block output families."""
import argparse,json,subprocess
from pathlib import Path
from qualify import ROOT,sha
from io_complete_candidate import c_core,c_half,hdl_wrapper,hdl_core
from c_read_candidate import generate
from io_wait_candidate import c_generate,hdl_generate,core_generate
HERE=Path(__file__).resolve().parent

def programs():
 p={}
 pre=bytes.fromhex('01 80 a5 11 45 23 21 00 80 36 5a 3e 5a')
 for name,prefix in [('immediate',b''),('dd-prefix',b'\xdd'),('fd-prefix',b'\xfd')]:p[name]=(pre+prefix+b'\xd3\x81\x76',0x5a)
 for i,value in enumerate([0xa5,0x80,0x23,0x45,0x80,0,0,0x5a]):p['ed-'+str(i)]=(pre+bytes([0xed,0x41+8*i,0x76]),value)
 for name,op in [('outi',0xa3),('outd',0xab),('otir',0xb3),('otdr',0xbb)]:p[name]=(pre+bytes([0x06,2,0xed,op,0x76]),0x5a)
 return p

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,default=ROOT/'build/keyboard-controller-io-write');a=ap.parse_args();out=a.out.resolve();out.mkdir(parents=True,exist_ok=True)
 def run(cmd):return subprocess.check_output(list(map(str,cmd)),text=True,timeout=30)
 c=(HERE/'io_wait_probe.c').read_text().replace('Z80_IORQ|Z80_RD','Z80_IORQ|Z80_WR').replace('Z80_SET_DATA(p,0x34);','')
 c=c.replace('unsigned selected=0;', 'unsigned selected=0,data=0;int stable=1;')
 c=c.replace('selected=Z80_GET_ADDR(p);','selected=Z80_GET_ADDR(p);data=Z80_GET_DATA(p);')
 c=c.replace('if(release<0&&Z80_GET_ADDR(p)!=selected)return 3;', 'if(release<0&&(Z80_GET_ADDR(p)!=selected||Z80_GET_DATA(p)!=data))stable=0;')
 c=c.replace(' return 0;', ' printf("DATA %u\\nSTABLE %d\\n",data,stable);\n return 0;')
 (out/'probe.c').write_text(c)
 h=(HERE/'io_wait_probe.v').read_text().replace('negedge rd_n','negedge wr_n').replace('wire read_active=!iorq_n&&!rd_n;', 'wire read_active=!iorq_n&&!wr_n;')
 h=h.replace('reg seen=0,released=0;', 'reg seen=0,released=0;reg [15:0] selected;reg [7:0] selected_data;integer stable=1;')
 h=h.replace('seen=1;origin=$time;', 'seen=1;origin=$time;selected=a;selected_data=dout;')
 h=h.replace('  $finish;', '  $display("DATA %0d",selected_data);$display("STABLE %0d",stable);\n  $finish;')
 h=h.replace('endmodule', 'always @(posedge clk or negedge clk)begin #1;if(seen&&!released&&(a!==selected||dout!==selected_data))stable=0;end\nendmodule')
 (out/'probe.v').write_text(h)
 run(['python3',HERE/'c_read_sampling.py','--out',out/'sampling'])
 vendor=ROOT/'third_party/cpu/tv80'
 for profile in ('old','candidate'):
  folder=out/profile;folder.mkdir(exist_ok=True)
  core=(ROOT/'third_party/cpu/chips/z80.h').read_text();half=(HERE/'c_read_half.h').read_text();wrap=(HERE/'tv80_io_candidate.v').read_text();rtlcore=(vendor/'tv80_core.v').read_text()
  (folder/'candidate.h').write_text((generate if profile=='old' else c_core)(core))
  (folder/'c_read_half.h').write_text((c_generate if profile=='old' else c_half)(half))
  (folder/'tv80_io_candidate.v').write_text((hdl_generate if profile=='old' else hdl_wrapper)(wrap))
  (folder/'tv80_core.v').write_text((core_generate if profile=='old' else hdl_core)(rtlcore))
  run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',folder,out/'probe.c','-o',folder/'probe'])
  rtl=[p for p in sorted(vendor.glob('*.v')) if p.name not in ('tv80_core.v','tv80n.v')]+[folder/'tv80_core.v',out/'sampling/tv80n_falling.v',folder/'tv80_io_candidate.v']
  run(['iverilog','-g2012','-s','probe','-o',folder/'probe.vvp',*rtl,out/'probe.v'])
 results=[]
 for name,(program,data) in programs().items():
  (out/'program.bin').write_bytes(program);(out/'program.hex').write_text('\n'.join(f'{x:02x}' for x in program)+'\n')
  for start,stop in [(1,2),(1,3),(1,4),(2,3),(2,4),(3,4),(3,5),(4,5),(4,6),(5,6),(1,8),(6,9)]:
   sample=3
   while start<=sample<stop:sample+=2
   row={'instruction':name,'start':start,'stop':stop,'expectedWidth':sample+2,'expectedData':data}
   for profile in ('old','candidate'):
    for lang in ('c','hdl'):
     folder=out/profile;cmd=[folder/'probe',start,stop,out/'program.bin'] if lang=='c' else ['vvp',folder/'probe.vvp',f'+start={start}',f'+stop={stop}','+rom='+str(out/'program.hex')]
     log=run(cmd);(folder/f'{name}-{lang}-{start}-{stop}.txt').write_text(log)
     vals={f[0]:int(f[1]) for line in log.splitlines() if (f:=line.split()) and f[0] in ('WIDTH','RELEASE','HALT','DATA','STABLE')}
     row[profile+'-'+lang]={'width':vals.get('RELEASE',vals.get('WIDTH')),'halt':vals['HALT'],'data':vals['DATA'],'stable':vals['STABLE']}
   results.append(row)
 report={'passed':all(r[k]=={'width':r['expectedWidth'],'halt':1,'data':r['expectedData'],'stable':1} for r in results for k in ('candidate-c','candidate-hdl')),'negativeControls':{k:any(r[k]['width']!=r['expectedWidth'] for r in results) for k in ('old-c','old-hdl')},'cases':results,'reference':'https://www.zilog.com/docs/z80/um0080.pdf','locator':'Figure 7','boundary':'First I/O write in each family; falling-edge WAIT acceptance, stable data/address, T3 falling release and program completion. Reset and analog setup/hold are separate.',
 'sources':{str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),HERE/'io_complete_candidate.py',HERE/'io_wait_candidate.py',HERE/'io_flags_candidate.py',HERE/'io_wait_probe.c',HERE/'io_wait_probe.v',HERE/'c_read_half.h',HERE/'c_read_candidate.py',HERE/'c_read_sampling.py',HERE/'c_read_half_test.c',HERE/'tv80_io_candidate.v',ROOT/'third_party/cpu/chips/z80.h',*sorted(vendor.glob('*.v'))]},
 'artifacts':{str(p.relative_to(out)):sha(p) for p in sorted(out.rglob('*')) if p.suffix in ('.txt','.h','.v','.c')}}
 (out/'assessment.json').write_text(json.dumps(report,indent=2)+'\n');print('Write boundaries:',report['passed'],report['negativeControls'])
 for r in results:
  if any(r[k]['width']!=r['expectedWidth'] or not r[k]['stable'] or r[k]['data']!=r['expectedData'] or not r[k]['halt'] for k in ('candidate-c','candidate-hdl')):print(r)
 if not report['passed'] or not all(report['negativeControls'].values()):raise SystemExit(1)
if __name__=='__main__':main()
