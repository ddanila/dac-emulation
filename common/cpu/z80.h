#ifndef DAC_Z80_H
#define DAC_Z80_H
#include "../../third_party/cpu/chips/z80.h"
/* One tick is one CPU clock. Memory and I/O callbacks perform bus actions;
 * an interrupt acknowledge is distinct from an ordinary I/O read. */
typedef struct {
  void *user;
  uint8_t (*read)(void *, uint16_t);
  void (*write)(void *, uint16_t, uint8_t);
  uint8_t (*input)(void *, uint16_t);
  void (*output)(void *, uint16_t, uint8_t);
  uint8_t (*ack)(void *);
} dac_z80_bus;
typedef struct {
  z80_t cpu;
  uint64_t pins, cycles;
  dac_z80_bus bus;
} dac_z80;
void dac_z80_init(dac_z80 *, dac_z80_bus);
void dac_z80_tick(dac_z80 *, int irq, int nmi);
#endif
