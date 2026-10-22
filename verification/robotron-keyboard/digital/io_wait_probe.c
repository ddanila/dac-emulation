#define CHIPS_IMPL
#include <c_read_half.h>
#include <stdio.h>
#include <stdlib.h>
int main(int argc,char **argv){
 if(argc!=4)return 2;
 int start=atoi(argv[1]),stop=atoi(argv[2]),origin=-1,release=-1;
 unsigned char mem[65536]={0};FILE *f=fopen(argv[3],"rb");if(!f)return 2;
 size_t n=fread(mem,1,sizeof mem,f);fclose(f);if(!n)return 2;
 unsigned selected=0;
 c_read_half c;c_read_reset(&c);uint64_t p=c.pins;
 for(int half=0;half<400;half++){
  int offset=origin<0?-1:half-origin;
  if(offset>=start&&offset<stop&&origin>=0)p|=Z80_WAIT;else p&=~Z80_WAIT;
  if(half%2==0)p=c_read_rise(&c,p);else p=c_read_fall(&c,p);
  int read=(p&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD);
  if(read&&origin<0){origin=half;selected=Z80_GET_ADDR(p);}
  if(origin>=0&&release<0&&!read)release=half;
  if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){Z80_SET_DATA(p,mem[Z80_GET_ADDR(p)]);}
  if((p&(Z80_MREQ|Z80_WR))==(Z80_MREQ|Z80_WR))mem[Z80_GET_ADDR(p)]=Z80_GET_DATA(p);
  if(read){Z80_SET_DATA(p,0x34);if(release<0&&Z80_GET_ADDR(p)!=selected)return 3;}
 }
 printf("WIDTH %d\nHALT %d\nA %d\n",release-origin,!!(p&Z80_HALT),c.cpu.a);
 return 0;
}
