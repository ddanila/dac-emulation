#ifndef DAC_PC1715_H
#define DAC_PC1715_H
#include "../../common/cpu/z80.h"
#include "../../common/trace/trace.h"
#include <stddef.h>

#define PC1715_CLOCK_HZ 2458000u

/* Native external-card seam. Callbacks happen once per I/O bus cycle, not once
 * per held CPU tick. All addresses are full Z80 addresses. read returns 1 when
 * driving data, 0 when unclaimed. The card owns its context; detach before freeing
 * it. No callback is a claim of physical /WAIT, /MEMDI or DMA support. */
typedef struct {
  void *user;
  int (*read)(void *, uint16_t address, uint8_t *data);
  void (*write)(void *, uint16_t address, uint8_t data);
  void (*tick)(void *, uint64_t cycle);
  int (*irq)(void *);
  uint8_t (*ack)(void *);
  void (*reti)(void *);
  void (*reset)(void *);
} pc1715_card;

/* Headless ordinary PC1715 motherboard bring-up. No W/M devices or CAS PROM.
 * Onboard CTC/SIO/CRT and the original PIO floppy board are not modelled yet. */
typedef struct {
  dac_z80 cpu;
  dac_trace_sink trace;
  pc1715_card card;
  uint8_t ram[65536], rom[2048];
  unsigned rom_enabled, io_active;
  uint8_t io_value;
  uint64_t io_reads, io_writes, unclaimed_reads;
} pc1715;

void pc1715_init(pc1715 *);
int pc1715_load(pc1715 *, const void *, size_t);
void pc1715_reset(pc1715 *); /* CPU/reset latch; retains ROM, RAM and card. */
int pc1715_attach(pc1715 *, const pc1715_card *); /* only before CPU execution */
void pc1715_run(pc1715 *, unsigned ticks);
uint8_t pc1715_read(void *, uint16_t);
void pc1715_write(void *, uint16_t, uint8_t);
#endif
