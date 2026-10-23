#include "../../../machines/robotron1715m/keyboard_cpu.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned char memory[65536];
static k7658_cpu cpu;
static unsigned cycle,wait_left,reset_left;
static int mode,reset_mode,late_mode,late,waited,reset_done,reset_pending;
static uint8_t read_mem(void *p,uint16_t a){(void)p;return memory[a];}
static void write_mem(void *p,uint16_t a,uint8_t d){
 (void)p;if(cpu.pins&Z80_WR)return;memory[a]=d;printf("MEM %u %u %u\n",cycle,a,d);
}
static uint8_t input(void *p,uint16_t a){
 (void)p;
 if(!(cpu.pins&Z80_IORQ)){
  if(mode&&!waited){wait_left=3;waited=1;}
  if(reset_mode&&!reset_done){reset_pending=1;reset_done=1;}
 }
 return late_mode?(late?0x34:0x12):((a^(a>>8)^0x5a)&255);
}
static void output(void *p,uint16_t a,uint8_t d){
 (void)p;if(!(cpu.pins&Z80_WR))printf("OUT %u %u %u\n",cycle,a,d);
}
static int consuming(unsigned step){
 switch(step){case 974:case 1188:case 1222:case 1256:case 1285:case 1314:case 1352:case 1390:case 1418:case 1463:case 1495:case 1537:case 1589:return 1;default:return 0;}
}
int main(int argc,char **argv){
 if(argc!=5)return 2;
 FILE *f=fopen(argv[1],"rb");
 if(!f)return 2;
 size_t n=fread(memory,1,sizeof memory,f);fclose(f);if(!n)return 2;
 mode=atoi(argv[2]);reset_mode=atoi(argv[3]);late_mode=atoi(argv[4]);
 k7658_cpu_init(&cpu,(dac_z80_bus){NULL,read_mem,write_mem,input,output,NULL});
 for(cycle=0;cycle<4000;cycle++){
  if(reset_left){reset_left--;continue;}
  cpu.wait=wait_left>0;if(wait_left)wait_left--;late=0;
  int sample=consuming(cpu.cpu.step);
  k7658_cpu_edge(&cpu,0,0,0);
  if(reset_pending){k7658_cpu_reset(&cpu);reset_left=16;reset_pending=0;printf("RESET %u\n",cycle);continue;}
  if(late_mode&&sample){late=1;printf("LATE %u 52\n",cycle);}
  k7658_cpu_edge(&cpu,1,0,0);
 }
 printf("FINAL %u %u %u %u %u\n",cpu.cpu.a,cpu.cpu.f,cpu.cpu.bc,cpu.cpu.hl,!!(cpu.pins&Z80_HALT));
 for(unsigned i=0x8000;i<0x8020;i++)printf("RAM %u %u\n",i,memory[i]);
 return 0;
}
