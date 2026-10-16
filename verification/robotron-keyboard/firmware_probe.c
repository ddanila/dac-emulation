#include "../../machines/robotron1715m/keyboard.h"
#include <stdio.h>
#include <stdlib.h>
static unsigned cycle;
static void bit(void *u,unsigned value){(void)u;printf("BIT %u %u\n",cycle,value);}
int main(int argc,char **argv){
 if(argc!=2)return 2;
 unsigned char rom[2048];FILE *f=fopen(argv[1],"rb");if(!f)return 2;
 if(fread(rom,1,sizeof rom,f)!=sizeof rom||fgetc(f)!=EOF)return 2;fclose(f);
 robotron_keyboard k;robotron_keyboard_init(&k,rom,NULL,bit);
 for(cycle=0;cycle<3200000;cycle++){
  if(cycle==200000)robotron_keyboard_key(&k,7,5,1);
  if(cycle==400000)robotron_keyboard_key(&k,7,5,0);
  if(cycle==600000)robotron_keyboard_key(&k,8,1,1);
  if(cycle==800000)robotron_keyboard_key(&k,7,5,1);
  if(cycle==1000000)robotron_keyboard_release(&k);
  if(cycle==1200000)robotron_keyboard_key(&k,8,7,1);
  if(cycle==1400000)robotron_keyboard_release(&k);
  if(cycle==1600000)robotron_keyboard_key(&k,8,0,1);
  if(cycle==1800000)robotron_keyboard_key(&k,7,5,1);
  if(cycle==2000000)robotron_keyboard_release(&k);
  if(cycle==2200000)robotron_keyboard_key(&k,7,5,1);
  if(cycle==2400000)robotron_keyboard_key(&k,8,6,1);
  if(cycle==2600000)robotron_keyboard_release(&k);
  if(cycle==2800000)robotron_keyboard_init(&k,rom,NULL,bit);
  if(cycle==3000000)robotron_keyboard_key(&k,7,5,1);
  unsigned old_leds=k.leds;
  if(cycle<2800000 || cycle>=2800016)dac_z80_tick(&k.cpu,0,0);
  if(k.leds!=old_leds)printf("EDGE %u %u\n",cycle,k.leds);
  if(cycle%200000==199999)printf("LED %u %u\n",cycle,k.leds);
 }
 return 0;
}
