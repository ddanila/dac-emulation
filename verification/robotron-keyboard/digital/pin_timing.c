/* Whole-T-state core: falling-edge rows are held observations, not pin claims. */
#define CHIPS_IMPL
#include "../../../third_party/cpu/chips/z80.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv) {
 if(argc!=5)return 2;
 int reset_at=atoi(argv[2]),wait_at=atoi(argv[3]),wait_end=atoi(argv[4]);
 unsigned char mem[65536]={0}; FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(mem,1,sizeof mem,f);fclose(f);if(!n)return 2;
 z80_t cpu;uint64_t p=z80_init(&cpu);
 for(int c=0;c<400;c++) {
  int reset=c>=reset_at&&c<reset_at+16,wait=c>=wait_at&&c<wait_end;
  if(c==reset_at)p=z80_reset(&cpu);
  if(!reset) {
   if(wait)p|=Z80_WAIT;else p&=~Z80_WAIT;
   p=z80_tick(&cpu,p);
   if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)) {Z80_SET_DATA(p,mem[Z80_GET_ADDR(p)]);}
   if((p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD)) {Z80_SET_DATA(p,0xa6);}
   if((p&(Z80_MREQ|Z80_WR))==(Z80_MREQ|Z80_WR))mem[Z80_GET_ADDR(p)]=Z80_GET_DATA(p);
  }
  for(int edge=0;edge<2;edge++)printf("PIN %d %d %d %d %u %u %d %d %d %d\n",c,edge,!reset,!wait,Z80_GET_ADDR(p),Z80_GET_DATA(p),!!(p&Z80_MREQ),!!(p&Z80_IORQ),!!(p&Z80_RD),!!(p&Z80_WR));
 }
 return 0;
}
