/* Count original monitor TTI returns during hold/release/repress intervals. */
#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>

int main(int argc,char **argv) {
  if(argc!=3)return 2;

  uint8_t rom[16384];FILE *f=fopen(argv[1],"rb");
  if(!f||fread(rom,1,sizeof rom,f)!=sizeof rom)return 2;
  fclose(f);
  juku *j=juku_create();if(!j||juku_load_rom(j,rom,sizeof rom)||juku_set_profile(j,atoi(argv[2])))return 2;
  j->kbd_enabled=1;while(j->cpu.cyc<4000000)juku_step(j);
  const uint8_t code[]={0x31,0,0x30,0xcd,0xd3,0xff,0x32,0x20,0x20,0x3a,0,0x20,0x3c,0x32,0,0x20,0xc3,3,1};
  for(unsigned i=0;i<sizeof code;i++)j->ram[0x100+i]=code[i];
  const uint8_t enter[]={0x3e,1,0xd3,6,0xc3,0,1};
  for(unsigned i=0;i<sizeof enter;i++)j->ram[0xc100+i]=enter[i];
  j->ram[0x2000]=0;j->cpu.pc=0xc100;
  for(unsigned phase=0;phase<5;phase++){
    if(phase==0||phase==2||phase==3)juku_key(j,'a',1);
    else juku_key(j,'a',0);
    unsigned long end=j->cpu.cyc+4000000;
    while(j->cpu.cyc<end)juku_step(j);
    printf("%u,%u,%02x\n",phase,j->ram[0x2000],j->ram[0x2020]);
  }
  juku_destroy(j);
}
