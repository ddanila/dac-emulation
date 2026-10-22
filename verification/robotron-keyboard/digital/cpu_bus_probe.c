#define CHIPS_IMPL
#include <cpu_bus_half.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc,char **argv) {
 if(argc!=9)return 2;
 unsigned char mem[65536]={0};FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(mem,1,sizeof mem,f);fclose(f);if(!n)return 2;
 int start=atoi(argv[2]),end=atoi(argv[3]),wait=atoi(argv[4]),wait_end=atoi(argv[5]),irq=atoi(argv[6]),nmi=atoi(argv[7]),late=atoi(argv[8]);
 cpu_bus_half cpu;cpu_bus_reset(&cpu);uint64_t p=cpu.pins;
 int outputs=0,last_output=0,old_write=0;
 for(int c=0;c<400;c++){
  p&=~(Z80_WAIT|Z80_INT|Z80_NMI);
  if(c>=wait&&c<wait_end)p|=Z80_WAIT;
  if(c>=irq&&c<irq+30)p|=Z80_INT;
  if(c==nmi)p|=Z80_NMI;
  for(int edge=0;edge<2;edge++){
   if(late<999 && Z80_GET_ADDR(p)==0x8000 && (p&Z80_RD)){
    Z80_SET_DATA(p,(c>late || (c==late&&edge))?0x34:0x12);
   }
   p=edge?cpu_bus_fall(&cpu,p):cpu_bus_rise(&cpu,p,c>=start&&c<end);
   unsigned a=Z80_GET_ADDR(p);
   if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){
    unsigned d=mem[a];if(late<999&&a==0x8000)d=(c>late || (c==late&&edge))?0x34:0x12;
    Z80_SET_DATA(p,d);
   }
   if((p&Z80_IORQ)&&(p&(Z80_RD|Z80_M1))){Z80_SET_DATA(p,0xff);}
   if((p&Z80_WR)&&!old_write){
    if(p&Z80_MREQ)mem[a]=Z80_GET_DATA(p);
    if(p&Z80_IORQ){outputs++;last_output=Z80_GET_DATA(p);}
   }
   old_write=!!(p&Z80_WR);
   printf("BUS %d %d %d %u\n",c,edge,cpu.busack,cpu.core.cpu.step);
  }
 }
 printf("RESULT %u %u %u\nOUTPUT %d %d\n",mem[32768],mem[32769],mem[32770],outputs,last_output);
 return 0;
}
