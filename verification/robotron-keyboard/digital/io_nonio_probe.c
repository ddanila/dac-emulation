#define CHIPS_IMPL
#ifdef HALF
#include <c_read_half.h>
#else
#include <candidate.h>
#endif
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
 if(argc!=3)return 2;
 unsigned char mem[65536]={0};FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 size_t n=fread(mem,1,sizeof mem,f);fclose(f);if(!n)return 2;
 int mode=atoi(argv[2]);
#ifdef HALF
 c_read_half model;c_read_reset(&model);uint64_t p=model.pins;
#else
 z80_t cpu;uint64_t p=z80_init(&cpu);
#endif
 int ack=0;
 for(int cycle=0;cycle<600;cycle++){
  p&=~(Z80_INT|Z80_NMI|Z80_WAIT);
  if(mode==1&&cycle>=200&&cycle<230)p|=Z80_INT;
  if(mode==2&&cycle==200)p|=Z80_NMI;
  if(mode==3&&cycle>=10&&cycle<15)p|=Z80_WAIT;
#ifdef HALF
  p=c_read_rise(&model,p);
#else
  p=z80_tick(&cpu,p);
#endif
  if((p&(Z80_IORQ|Z80_M1))==(Z80_IORQ|Z80_M1)){Z80_SET_DATA(p,0xff);ack++;}
  if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){Z80_SET_DATA(p,mem[Z80_GET_ADDR(p)]);}
  if((p&(Z80_MREQ|Z80_WR))==(Z80_MREQ|Z80_WR))mem[Z80_GET_ADDR(p)]=Z80_GET_DATA(p);
  printf("PIN %d %llu\n",cycle,(unsigned long long)p);
#ifdef HALF
  p=c_read_fall(&model,p);
#endif
 }
 printf("RESULT %u %u %u %d\n",mem[0x8000],mem[0x8001],mem[0x8002],ack);
 return 0;
}
