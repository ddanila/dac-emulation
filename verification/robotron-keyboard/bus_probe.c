#include "../../machines/robotron1715m/keyboard.h"
#include <stdio.h>
static unsigned serial_count,serial_bit;
static void serial(void *u,unsigned bit){(void)u;serial_count++;serial_bit=bit;}
int main(int argc,char **argv){
 (void)argv;int smoke=argc>1;
 uint8_t rom[2048]={0};robotron_keyboard k;robotron_keyboard_init(&k,rom,NULL,serial);
 // Distinct row bits expose OR versus AND when several columns are selected.
 for(unsigned c=0;c<13;c++)k.matrix[c]=(uint8_t)(1u<<(c%8));
 if(smoke)for(unsigned i=0;i<5;i++){
  unsigned a=(i%4)<<13;k.cpu.pins=0;
  unsigned v=k.cpu.bus.input(k.cpu.bus.user,(uint16_t)a);
  printf("0 %04x 00 %02x %x 0 0\n",a,v,k.leds);
 }
 for(unsigned a=0;a<65536;a++){
  unsigned mask=a&0x1fff;if(smoke && ((a&0xe000)!=0x8000 || !mask || (mask&(mask-1))))continue;
  k.cpu.pins=0;unsigned v=k.cpu.bus.input(k.cpu.bus.user,(uint16_t)a);
  printf("0 %04x 00 %02x %x 0 0\n",a,v,k.leds);
 }
 for(unsigned a=0;a<(smoke?8192u:32768u);a++){
  k.cpu.pins=0;unsigned before=serial_count;unsigned d=(a*37)^0xa5;
  k.cpu.bus.output(k.cpu.bus.user,(uint16_t)a,(uint8_t)d);
  printf("1 %04x %02x 00 %x %x %x\n",a,d&255,k.leds,serial_count-before,serial_bit);
 }
 return 0;
}
