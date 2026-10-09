#define CHIPS_IMPL
#include "z80.h"
void dac_z80_init(dac_z80 *c, dac_z80_bus bus) {
  c->bus = bus;
  c->cycles = 0;
  c->pins = z80_init(&c->cpu);
}
void dac_z80_tick(dac_z80 *c, int irq, int nmi) {
  uint64_t p = (c->pins & ~(Z80_INT | Z80_NMI)) | (irq ? Z80_INT : 0) |
               (nmi ? Z80_NMI : 0);
  p = z80_tick(&c->cpu, p);
  uint16_t a = Z80_GET_ADDR(p);
  uint8_t d = 0xff;
  if (p & Z80_MREQ) {
    if (p & Z80_RD) {
      d = c->bus.read(c->bus.user, a);
      Z80_SET_DATA(p, d);
    } else if (p & Z80_WR)
      c->bus.write(c->bus.user, a, Z80_GET_DATA(p));
  } else if (p & Z80_IORQ) {
    if (p & Z80_M1) {
      d = c->bus.ack ? c->bus.ack(c->bus.user) : 0xff;
      Z80_SET_DATA(p, d);
    } else if (p & Z80_RD) {
      d = c->bus.input ? c->bus.input(c->bus.user, a) : 0xff;
      Z80_SET_DATA(p, d);
    } else if ((p & Z80_WR) && c->bus.output)
      c->bus.output(c->bus.user, a, Z80_GET_DATA(p));
  }
  c->pins = p;
  c->cycles++;
}
