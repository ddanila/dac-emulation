/* Experimental machine-cycle arbitration around the qualified I/O core.
 * A side-effect-free core preview identifies the next bus cycle; callbacks
 * are performed only by the caller on committed output pins. */
#include "c_read_half.h"
#include "cpu_bus_states.h"
typedef struct {
 c_read_half core;
 uint64_t pins;
 int busack,request,started;
} cpu_bus_half;
static void cpu_bus_reset(cpu_bus_half *c) {
 c_read_reset(&c->core);c->pins=c->core.pins;
 c->busack=c->request=c->started=0;
}
static uint64_t cpu_bus_rise(cpu_bus_half *c,uint64_t pins,int request) {
 c_read_half preview=c->core;
 uint64_t internal=(pins&~(Z80_CTRL_PIN_MASK))|(c->core.pins&Z80_CTRL_PIN_MASK);
 uint64_t next=c_read_rise(&preview,internal);
 int boundary=(next&Z80_M1) || cpu_bus_internal(c->core.cpu.step) ||
  (cpu_bus_t2(&preview.cpu) && preview.cpu.step!=c->core.cpu.step);
 c->busack=c->request && (c->busack || (c->started && boundary));
 c->request=request;c->started=1;
 if(c->busack){
  /* NMI is edge latched while ownership is external, serviced after release. */
  uint64_t rising=(internal^c->core.cpu.pins)&internal&Z80_NMI;
  c->core.cpu.int_bits=((c->core.cpu.int_bits|rising)&Z80_NMI)|(internal&Z80_INT);
  c->core.cpu.pins=(c->core.cpu.pins&~(Z80_NMI|Z80_INT))|(internal&(Z80_NMI|Z80_INT));
  c->pins=internal&~Z80_CTRL_PIN_MASK;
 }
 else {c->core=preview;c->pins=next;}
 return c->pins;
}
static uint64_t cpu_bus_fall(cpu_bus_half *c,uint64_t pins) {
 if(c->busack)return c->pins;
 return c->pins=c_read_fall(&c->core,pins);
}
