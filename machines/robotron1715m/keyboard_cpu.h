#ifndef DAC_K7658_CPU_H
#define DAC_K7658_CPU_H
#include "../../common/cpu/z80.h"
#include "generated/keyboard_cpu/cpu_bus_pins.h"
typedef struct {
  k7658_z80_t cpu;
  uint64_t pins, cycles;
  dac_z80_bus bus;
  cpu_bus_pins controller;
  unsigned bus_request, wait;
} k7658_cpu;
void k7658_cpu_init(k7658_cpu *, dac_z80_bus);
void k7658_cpu_reset(k7658_cpu *);
/* Paired rising/falling calls expose the same bus interface to co-simulation.
 * Inputs may change between edges. Whole-clock callers use tick. */
uint64_t k7658_cpu_edge(k7658_cpu *, int falling, int irq, int nmi);
int k7658_cpu_valid_state(const k7658_cpu *);
int k7658_cpu_bus_acknowledged(const k7658_cpu *);
void k7658_cpu_tick(k7658_cpu *, int irq, int nmi);
#endif
