#!/usr/bin/env python3
"""Install the qualified-candidate bus boundary into an isolated runtime shadow."""
import re
from cpu_bus_c import generate
from io_flags_candidate import replace_once

CPU = r'''#define CHIPS_IMPL
#include "z80.h"
void dac_z80_init(dac_z80 *c,dac_z80_bus bus) {
 c->bus=bus;c->cycles=0;cpu_pins_reset(&c->controller);
 c->cpu=c->controller.core.core.cpu;c->pins=c->controller.pins;
}
void dac_z80_tick(dac_z80 *c,int irq,int nmi) {
 uint64_t p=(c->pins&~(Z80_INT|Z80_NMI))|(irq?Z80_INT:0)|(nmi?Z80_NMI:0);
 for(int edge=0;edge<2;edge++){
  p=edge?cpu_pins_fall(&c->controller,p):cpu_pins_rise(&c->controller,p,0);
  uint16_t a=Z80_GET_ADDR(p);uint8_t d=0xff;
  if(p&Z80_MREQ){
   if(p&Z80_RD){d=c->bus.read(c->bus.user,a);Z80_SET_DATA(p,d);}
   else if(p&Z80_WR)c->bus.write(c->bus.user,a,Z80_GET_DATA(p));
  }else if(p&Z80_IORQ){
   if(p&Z80_M1){d=c->bus.ack?c->bus.ack(c->bus.user):0xff;Z80_SET_DATA(p,d);}
   else if(p&Z80_RD){d=c->bus.input?c->bus.input(c->bus.user,a):0xff;Z80_SET_DATA(p,d);}
   else if((p&Z80_WR)&&c->bus.output)c->bus.output(c->bus.user,a,Z80_GET_DATA(p));
  }
  c->pins=p;
 }
 c->cpu=c->controller.core.core.cpu;c->cycles++;
}
'''


def integrate_shadow(root):
    folder=root/'common/cpu'
    generate(folder)
    for name in ('c_read_half.h','cpu_bus_states.h','cpu_bus_half.h','cpu_bus_pins.h'):
        path=folder/name
        text=path.read_text().replace('#include "candidate.h"','/* CPU declarations already included by z80.h. */')
        path.write_text(re.sub(r'\bstatic (?!inline)', 'static inline ', text))
    path=folder/'z80.h';text=path.read_text()
    text=replace_once(text,'/* One tick', '#include "cpu_bus_pins.h"\n/* One tick')
    text=replace_once(text,'  dac_z80_bus bus;', '  dac_z80_bus bus;\n  cpu_bus_pins controller;')
    path.write_text(text)
    (folder/'z80.c').write_text(CPU)
