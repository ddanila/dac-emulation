#ifndef DAC_VJUGA_H
#define DAC_VJUGA_H
#include "../../common/cpu/z80.h"
#include <stddef.h>
/* Functional Rev-A bounded-boot profile. No DRAM waits, IRQ or FDC yet. */
typedef struct {
  dac_z80 cpu;
  uint8_t rom[16384], ram[65536], ports[256], portc;
  uint64_t video_writes;
  unsigned decode_mode;
} vjuga;
void vjuga_init(vjuga *, unsigned decode_mode);
int vjuga_load_rom(vjuga *, const void *, size_t);
void vjuga_run(vjuga *, unsigned ticks);
uint8_t vjuga_read(void *, uint16_t);
void vjuga_write(void *, uint16_t, uint8_t);
#endif
