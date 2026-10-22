#include "../../machines/robotron1715m/keyboard_board.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned serial_count,serial_value;
static void serial(void *user,unsigned bit){(void)user;serial_count++;serial_value=bit;}
int main(void){
  unsigned char rom[2048]={0x01,0x01,0x80,0xed,0x78,0xed,0x79,0x76};
  robotron_keyboard k;robotron_keyboard_init(&k,rom,NULL,serial);
  assert(!k.leds_known);
  for(unsigned i=0;i<6;i++)k7658_cpu_tick(&k.cpu,0,0);
  robotron_keyboard_bus_request(&k,1);
  unsigned clocks=0;
  while(!k7658_cpu_bus_acknowledged(&k.cpu)&&clocks++<16)k7658_cpu_tick(&k.cpu,0,0);
  assert(k7658_cpu_bus_acknowledged(&k.cpu));
  k7658_z80_t held=k.cpu.cpu;
  for(unsigned i=0;i<20;i++){
    k7658_cpu_tick(&k.cpu,0,0);
    assert(!(k.cpu.pins&Z80_CTRL_PIN_MASK));
    assert(!memcmp(&held,&k.cpu.cpu,sizeof held));
  }
  assert(!k.leds_known&&!serial_count);
  robotron_keyboard_bus_request(&k,0);k.matrix[0]=1;
  unsigned changed=0;
  for(unsigned i=0;i<300;i++){
    k7658_cpu_edge(&k.cpu,0,0,0);
    if((k.cpu.pins&(Z80_IORQ|Z80_RD))==(Z80_IORQ|Z80_RD)){
      assert(k.leds_known);k.matrix[0]=2;changed=1;
    }
    k7658_cpu_edge(&k.cpu,1,0,0);
  }
  assert(changed&&serial_count==1&&serial_value==0);
  assert(k.leds_known&&k.matrix[0]==2);
  unsigned leds=k.leds;uint64_t cycles=k.cpu.cycles,strobes=k.strobes;
  robotron_keyboard_reset(&k);
  assert(k.leds_known&&k.leds==leds&&k.matrix[0]==2&&k.strobes==strobes);
  assert(k.cpu.cycles==cycles&&!(k.cpu.pins&Z80_CTRL_PIN_MASK));
  for(unsigned initial=0;initial<4;initial++){
    robotron_keyboard_init(&k,rom,NULL,serial);k.leds=initial;
    assert(!k.leds_known);
    for(unsigned i=0;i<100&&!k.leds_known;i++)k7658_cpu_tick(&k.cpu,0,0);
    assert(k.leds_known&&k.leds==0);
  }
  memset(rom,0,sizeof rom);rom[0]=0xfb;rom[1]=0x76;
  robotron_keyboard_init(&k,rom,NULL,serial);k.leds=3;
  for(unsigned i=0;i<16;i++)k7658_cpu_tick(&k.cpu,0,0);
  assert(!k.leds_known);
  for(unsigned i=0;i<40&&!k.leds_known;i++)k7658_cpu_tick(&k.cpu,1,0);
  assert(k.leds_known&&k.leds==0); /* Interrupt IORQ also clocks A6. */
  puts("Keyboard backend: bus ownership, live matrix, LED validity and CPU reset passed");
}
