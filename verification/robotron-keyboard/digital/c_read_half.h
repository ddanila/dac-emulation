/* Experimental I/O-only half-cycle adapter over the generated C core.
 * One rising call per T-state; every rising call must have a falling call.
 * Supply live bus data before the falling call. Reset cancels pending work.
 * Non-I/O behavior retains the original whole-cycle model. */
#include "candidate.h"
typedef struct { z80_t cpu; uint64_t pins; int pending; } c_read_half;
static int c_read_consuming(unsigned step) {
 switch(step){case 974:case 1188:case 1222:case 1256:case 1285:case 1314:case 1352:case 1390:case 1418:case 1463:case 1495:case 1537:case 1589:return 1;default:return 0;}
}
static void c_read_reset(c_read_half *c) {
 c->pins=z80_init(&c->cpu);c->pending=0;
}
static uint64_t c_read_rise(c_read_half *c,uint64_t pins) {
 c->pending=c_read_consuming(c->cpu.step);
 c->pins=c->pending?pins:z80_tick(&c->cpu,pins);
 return c->pins;
}
static uint64_t c_read_fall(c_read_half *c,uint64_t pins) {
 if(c->pending){
  c->pins=z80_tick(&c->cpu,pins);
  // Release after sampling at T3 falling; internal register changes precede
  // the next rising-edge machine cycle. No instruction T-state is added.
  c->pins&=~(Z80_IORQ|Z80_RD);c->pending=0;
 }else c->pins=pins;
 return c->pins;
}
