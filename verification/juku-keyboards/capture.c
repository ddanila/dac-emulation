/* Run each host key through the original monitor's TTI entry point. */
#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned keys[255];
int main(int argc,char **argv) {
  if(argc!=3)return 2;
  for(unsigned i=0;i<255;i++)keys[i]=i+1;
  uint8_t rom[16384];FILE *f=fopen(argv[1],"rb");
  if(!f||fread(rom,1,sizeof rom,f)!=sizeof rom)return 2;
  fclose(f);
  for(unsigned k=0;k<sizeof keys/sizeof *keys;k++) {
    juku *j=juku_create();if(!j||juku_load_rom(j,rom,sizeof rom)||juku_set_profile(j,atoi(argv[2])))return 2;
    j->kbd_enabled=1;
    while(j->cpu.cyc<4000000)juku_step(j);
    const uint8_t code[]={0x31,0,0x30,0xcd,0xd3,0xff,0x32,0,0x20,0x3e,0xd3,0x32,1,0x20,0x76};
    for(unsigned i=0;i<sizeof code;i++)j->ram[0x100+i]=code[i];
    const uint8_t enter[]={0x3e,1,0xd3,6,0xc3,0,1};
    for(unsigned i=0;i<sizeof enter;i++)j->ram[0xc100+i]=enter[i];
    j->ram[0x2001]=0;j->cpu.pc=0xc100;juku_key(j,keys[k],1);
    unsigned long end=j->cpu.cyc+600000;
    while(j->ram[0x2001]!=0xd3&&j->cpu.cyc<end)juku_step(j);
    printf("%02x,%d,%02x",keys[k],j->ram[0x2001]==0xd3,j->ram[0x2000]);
    putchar('\n');juku_key(j,keys[k],0);juku_destroy(j);
  }
}
