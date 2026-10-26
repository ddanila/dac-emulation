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
  /* Optional native transaction wait: nonzero defers read/write callbacks.
   * Called repeatedly with the same address/direction while CPU microsteps
   * pause and card/clock ticks continue. No M1/ack or memory waits. This is a
   * T-state transaction abstraction, not a half-clock /WAIT sampling model. */
  int (*wait)(void *, uint16_t address, int write);
} pc1715_card;

/* Headless ordinary PC1715 motherboard bring-up. No W/M devices or CAS PROM.
 * CTC/SIO register-level interrupt subset is opt-in; CRT and the original
 * PIO floppy board remain external/unmodelled. */
typedef struct {
  uint16_t count, reload, divider;
  uint8_t control, waiting, running, pending, service, level;
} pc1715_ctc;
typedef struct {
  uint8_t wr[8], pointer, fifo[3], count, pending[3], service[3];
  uint8_t first, tx_busy, errors;
} pc1715_sio;
typedef struct {
  dac_z80 cpu;
  dac_trace_sink trace;
  pc1715_card card;
  unsigned onboard, card_service, card_offline;
  uint8_t ctc_vector;
  pc1715_ctc ctc[4];
  pc1715_sio sio[2];
  uint8_t ram[65536], rom[2048];
  unsigned rom_enabled, io_active, io_waiting;
  uint8_t io_value;
  uint64_t io_reads, io_writes, unclaimed_reads;
  uint64_t wait_ticks;
} pc1715;

void pc1715_init(pc1715 *);
int pc1715_load(pc1715 *, const void *, size_t);
void pc1715_reset(pc1715 *); /* CPU/reset latch; retains ROM, RAM and card. */
int pc1715_attach(pc1715 *, const pc1715_card *); /* only before CPU execution */
/* Opt-in native peripherals; legacy external keyboard fixtures remain default. */
int pc1715_onboard_enable(pc1715 *);
int pc1715_onboard_read(pc1715 *,uint16_t,uint8_t *);
int pc1715_onboard_write(pc1715 *,uint16_t,uint8_t);
void pc1715_ctc_input(pc1715 *,unsigned channel,int level);
int pc1715_sio_receive(pc1715 *,unsigned channel,uint8_t); /* completed byte seam */
void pc1715_sio_external(pc1715 *,unsigned channel); /* external/status transition */
int pc1715_irq_pending(pc1715 *);
uint8_t pc1715_irq_ack(pc1715 *);
void pc1715_irq_reti(pc1715 *);
void pc1715_card_quiesce(pc1715 *); /* release chain and bus until board reset */
void pc1715_run(pc1715 *, unsigned ticks);
uint8_t pc1715_read(void *, uint16_t);
void pc1715_write(void *, uint16_t, uint8_t);
#endif
