#!/usr/bin/env python3
"""Behavioral address/control checks for the C half-cycle I/O contract."""
import subprocess,tempfile,unittest
from pathlib import Path
from c_read_candidate import generate
from c_read_instructions import programs
from qualify import ROOT
HERE=Path(__file__).resolve().parent
DRIVER=r'''
#define CHIPS_IMPL
#include "c_read_half.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
 if(argc!=3)return 2;
 unsigned char mem[65536]={0};FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 if(!fread(mem,1,sizeof mem,f))return 2;fclose(f);
 c_read_half c;c_read_reset(&c);uint64_t p=c.pins;int left=0,waited=0;
 for(int cycle=0;cycle<600;cycle++){
  if(left){p|=Z80_WAIT;left--;}else p&=~Z80_WAIT;
  p=c_read_rise(&c,p);
  if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){Z80_SET_DATA(p,mem[Z80_GET_ADDR(p)]);}
  if((p&(Z80_MREQ|Z80_WR))==(Z80_MREQ|Z80_WR))mem[Z80_GET_ADDR(p)]=Z80_GET_DATA(p);
  if((p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD)){
   Z80_SET_DATA(p,0x34);
   if(atoi(argv[2])&&!waited){left=3;waited=1;}
  }
  printf("%d %u %d\n",cycle*2,Z80_GET_ADDR(p),(p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD));
  p=c_read_fall(&c,p);
  printf("%d %u %d\n",cycle*2+1,Z80_GET_ADDR(p),(p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD));
 }
 return 0;
}
'''
class Contract(unittest.TestCase):
 def test_t1_address_t2_assertion_and_t3_falling_release(self):
  with tempfile.TemporaryDirectory() as temp:
   out=Path(temp);(out/'candidate.h').write_text(generate((ROOT/'third_party/cpu/chips/z80.h').read_text()));(out/'probe.c').write_text(DRIVER)
   subprocess.run(['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',str(out),'-I',str(HERE),str(out/'probe.c'),'-o',str(out/'probe')],check=True)
   for name,program in programs().items():
    if name=='indexed-memory' or name.startswith(('out','ot')):continue
    (out/'rom.bin').write_bytes(program)
    for wait in (0,1):
     with self.subTest(instruction=name,wait=wait):
      log=subprocess.check_output([str(out/'probe'),str(out/'rom.bin'),str(wait)],text=True)
      rows=[list(map(int,l.split())) for l in log.splitlines()];bursts=[]
      for i,r in enumerate(rows):
       if r[2] and (i==0 or not rows[i-1][2]):
        end=next(j for j in range(i+1,len(rows)) if not rows[j][2]);bursts.append((i,end))
        self.assertEqual(i%2,0);self.assertEqual(end%2,1)
        self.assertEqual(rows[i-2][1],r[1], 'address must precede assertion by a whole T-state')
        self.assertTrue(all(v[1]==r[1] for v in rows[i-2:end]))
      self.assertTrue(bursts)
      self.assertEqual([end-start for start,end in bursts],[11 if wait and i==0 else 5 for i in range(len(bursts))])
if __name__=='__main__':unittest.main()
