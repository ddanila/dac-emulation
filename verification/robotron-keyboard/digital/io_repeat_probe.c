#define CHIPS_IMPL
#include <c_read_half.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
 if(argc!=4)return 2;
 unsigned char mem[65536]={0};FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(mem,1,sizeof mem,f);fclose(f);if(!n)return 2;
 int mode=atoi(argv[2]);unsigned data=atoi(argv[3]);
 c_read_half c;c_read_reset(&c);uint64_t p=c.pins;int trigger=0,accesses=0,previous=0;
 for(int cycle=0;cycle<600;cycle++){
  if(trigger)p|=mode?Z80_NMI:Z80_INT;
  p=c_read_rise(&c,p);
  if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){Z80_SET_DATA(p,mem[Z80_GET_ADDR(p)]);}
  if((p&(Z80_MREQ|Z80_WR))==(Z80_MREQ|Z80_WR))mem[Z80_GET_ADDR(p)]=Z80_GET_DATA(p);
  int io=(p&Z80_IORQ)&&!(p&Z80_M1);
  if(io&&!previous){accesses++;trigger=1;}
  previous=io;
  if((p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD)){Z80_SET_DATA(p,data);}
  if((p&(Z80_IORQ|Z80_M1))==(Z80_IORQ|Z80_M1)){Z80_SET_DATA(p,0xff);}
  p=c_read_fall(&c,p);
 }
 printf("RESULT %u %u %d %d\n",mem[0x9000],mem[0x9001],accesses,!!(p&Z80_HALT));
 return 0;
}
