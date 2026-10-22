/* Include the shared declarations before enabling this backend's implementation. */
#include "../../common/cpu/z80.h"
#define CHIPS_IMPL
#include "keyboard_cpu.h"
void k7658_cpu_reset(k7658_cpu *c) {
  cpu_pins_reset(&c->controller);
  c->cpu=c->controller.core.core.cpu;c->pins=c->controller.pins;
}
void k7658_cpu_init(k7658_cpu *c,dac_z80_bus bus) {
  c->bus=bus;c->cycles=0;c->bus_request=c->wait=0;
  k7658_cpu_reset(c);
}
uint64_t k7658_cpu_edge(k7658_cpu *c,int falling,int irq,int nmi) {
  uint64_t p=(c->pins&~(Z80_INT|Z80_NMI|Z80_WAIT))|
    (irq?Z80_INT:0)|(nmi?Z80_NMI:0)|(c->wait?Z80_WAIT:0);
  /* Resolve live input pins before the sampling edge. A4 is transparent;
   * an input change between T3 rising and falling must reach the CPU. */
  if((p&(Z80_MREQ|Z80_RD))==(Z80_MREQ|Z80_RD)){
    uint8_t d=c->bus.read(c->bus.user,Z80_GET_ADDR(p));Z80_SET_DATA(p,d);
  }else if(p&Z80_IORQ){
    if(p&Z80_M1){uint8_t d=c->bus.ack?c->bus.ack(c->bus.user):0xff;Z80_SET_DATA(p,d);}
    else if(p&Z80_RD){uint8_t d=c->bus.input?c->bus.input(c->bus.user,Z80_GET_ADDR(p)):0xff;Z80_SET_DATA(p,d);}
  }
  p=falling?cpu_pins_fall(&c->controller,p):cpu_pins_rise(&c->controller,p,c->bus_request);
  uint16_t a=Z80_GET_ADDR(p);uint8_t d=0xff;
  if(p&Z80_MREQ){
    if(p&Z80_RD){d=c->bus.read(c->bus.user,a);Z80_SET_DATA(p,d);}
    else if(p&Z80_WR)c->bus.write(c->bus.user,a,Z80_GET_DATA(p));
  }else if(p&Z80_IORQ){
    if(p&Z80_M1){d=c->bus.ack?c->bus.ack(c->bus.user):0xff;Z80_SET_DATA(p,d);}
    else if(p&Z80_RD){d=c->bus.input?c->bus.input(c->bus.user,a):0xff;Z80_SET_DATA(p,d);}
    else if((p&Z80_WR)&&c->bus.output)c->bus.output(c->bus.user,a,Z80_GET_DATA(p));
  }
  c->pins=p;c->cpu=c->controller.core.core.cpu;
  if(falling)c->cycles++;
  return p;
}
void k7658_cpu_tick(k7658_cpu *c,int irq,int nmi) {
  k7658_cpu_edge(c,0,irq,nmi);k7658_cpu_edge(c,1,irq,nmi);
}

int k7658_cpu_bus_acknowledged(const k7658_cpu *c) {
  return c->controller.core.busack;
}

int k7658_cpu_valid_state(const k7658_cpu *c) {
  const cpu_bus_pins *p=&c->controller;
  return c->cpu.step<=1708 && c->cpu.hlx_idx<3 && c->cpu.im<3 &&
    !memcmp(&c->cpu,&p->core.core.cpu,sizeof(c->cpu)) &&
    c->bus_request<=1 && c->wait<=1 && p->kind<=4 && p->phase<=8 &&
    p->address<=65535 && p->data<=255 && (unsigned)p->core.busack<=1 &&
    (unsigned)p->core.request<=1 && (unsigned)p->core.started<=1 &&
    (unsigned)p->core.core.pending<=7 && (unsigned)p->core.core.fetch_ready<=1;
}
