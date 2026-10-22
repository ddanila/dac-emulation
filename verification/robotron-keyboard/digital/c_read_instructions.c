#define CHIPS_IMPL
#include "candidate.h"
#include <stdio.h>
#include <stdlib.h>
static int consuming(unsigned step) {
 switch(step){case 974:case 1188:case 1222:case 1256:case 1285:case 1314:case 1352:case 1390:case 1418:case 1463:case 1495:case 1537:case 1589:return 1;default:return 0;}
}
int main(int argc,char **argv){
 if(argc!=5)return 2;
 unsigned char memory[65536]={0};FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(memory,1,sizeof memory,f);fclose(f);if(!n)return 2;
 int mode=atoi(argv[2]),reset_mode=atoi(argv[3]),late_mode=atoi(argv[4]);
 z80_t cpu;uint64_t p=z80_init(&cpu);unsigned wait_left=0,reset_left=0;int waited=0,reset_done=0,previous_read=0,previous_write=0;
 for(unsigned cycle=0;cycle<4000;cycle++){
  if(reset_left){reset_left--;continue;}
  if(wait_left){p|=Z80_WAIT;wait_left--;}else p&=~Z80_WAIT;
  int sample=consuming(cpu.step);
  p=z80_tick(&cpu,p);
  unsigned address=Z80_GET_ADDR(p);int read=(p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD),write=!!(p&Z80_WR);
  if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){Z80_SET_DATA(p,memory[address]);}
  if(read){
   unsigned data=late_mode?0x12:((address^(address>>8)^0x5a)&255);
   Z80_SET_DATA(p,data);
   printf("READ %u %u %u %d %d\n",cycle,address,data,!!(p&Z80_WAIT),sample);
   if(!previous_read){
    if(mode&&!waited){wait_left=3;waited=1;}
    if(reset_mode&&!reset_done){p=z80_reset(&cpu);reset_left=16;reset_done=1;previous_read=previous_write=0;printf("RESET %u\n",cycle);continue;}
   }
   // A legal late value after the T3 rising sample, before T3 falling.
   if(late_mode&&sample){Z80_SET_DATA(p,0x34);printf("LATE %u 52\n",cycle);}
  }
  if(write&&!previous_write){
   unsigned data=Z80_GET_DATA(p);
   if(p&Z80_MREQ){memory[address]=data;printf("MEM %u %u %u\n",cycle,address,data);}
   if(p&Z80_IORQ)printf("OUT %u %u %u\n",cycle,address,data);
  }
  previous_read=read;previous_write=write;
 }
 printf("FINAL %u %u %u %u %u\n",cpu.a,cpu.f,cpu.bc,cpu.hl,!!(p&Z80_HALT));
 for(unsigned i=0x8000;i<0x8020;i++)printf("RAM %u %u\n",i,memory[i]);
 return 0;
}
