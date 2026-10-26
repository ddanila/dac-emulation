/* MIT. Independent ordinary-PC1715 CPU/memory/bus model.
 * Sources and unsupported devices are documented in README.md. */
#include "pc1715.h"
#include <errno.h>
#include <string.h>
#include "peripherals.h"

static void trace(pc1715 *m, const char *kind, uint16_t a, uint8_t data,
                  unsigned space, uint32_t offset) {
  dac_trace_access(&m->trace, kind, a, data, m->cpu.cycles, 3,
                   DAC_MASTER_CPU, space, offset);
}
uint8_t pc1715_read(void *p, uint16_t a) {
  pc1715 *m = p;
  int rom = m->rom_enabled && a < sizeof(m->rom);
  uint8_t data = rom ? m->rom[a] : m->ram[a];
  trace(m, "MR", a, data, rom ? DAC_SPACE_ROM : DAC_SPACE_RAM, a);
  return data;
}
void pc1715_write(void *p, uint16_t a, uint8_t data) {
  pc1715 *m = p;
  /* The boot ROM copies itself into RAM before OUT (28h),A. */
  m->ram[a] = data;
  trace(m, "MW", a, data, DAC_SPACE_RAM, a);
}
static uint8_t input(void *p, uint16_t a) {
  pc1715 *m = p;
  if (!m->io_active) {
    if (!m->card_offline && !(m->onboard && (a&255)>=8 && (a&255)<=15) && m->card.wait && m->card.wait(m->card.user, a, 0)) {
      m->io_waiting = 1;
      return 0xff;
    }
    m->io_active = 1;
    m->io_value = 0xff;
    uint8_t value = 0xff;
    if (pc1715_onboard_read(m,a,&value) || (!m->card_offline && m->card.read && m->card.read(m->card.user, a, &value)))
      m->io_value = value;
    else
      m->unclaimed_reads++;
    m->io_reads++;
    trace(m, "IR", a, m->io_value, DAC_SPACE_IO, a & 255);
  }
  return m->io_value;
}
static void output(void *p, uint16_t a, uint8_t data) {
  pc1715 *m = p;
  if (m->io_active)
    return;
  if (!m->card_offline && !(m->onboard && (a&255)>=8 && (a&255)<=15) && m->card.wait && m->card.wait(m->card.user, a, 1)) {
    m->io_waiting = 1;
    return;
  }
  m->io_active = 1;
  m->io_writes++;
  trace(m, "IW", a, data, DAC_SPACE_IO, a & 255);
  /* A2..A7 decode MEMCS1, ignoring A0/A1 and the upper I/O address byte. */
  if ((a & 0xfc) == 0x28)
    m->rom_enabled = 0;
  if (!pc1715_onboard_write(m,a,data) && !m->card_offline && m->card.write)
    m->card.write(m->card.user, a, data);
}
static uint8_t acknowledge(void *p) {
  pc1715 *m = p;
  if (!m->io_active) {
    m->io_active = 1;
    m->io_value = pc1715_irq_ack(m);
    trace(m, "IA", 0, m->io_value, DAC_SPACE_UNKNOWN, 0);
  }
  return m->io_value;
}
void pc1715_reset(pc1715 *m) {
  m->card_service=m->card_offline=0;
  m->ctc_vector=0;memset(m->ctc,0,sizeof(m->ctc));memset(m->sio,0,sizeof(m->sio));
  m->rom_enabled = 1;
  m->io_active = 0;
  m->io_waiting = 0;
  m->wait_ticks = 0;
  m->io_value = 0xff;
  m->io_reads = m->io_writes = m->unclaimed_reads = 0;
  dac_z80_init(&m->cpu, (dac_z80_bus){m, pc1715_read, pc1715_write,
                                      input, output, acknowledge});
  if (m->card.reset)
    m->card.reset(m->card.user);
}
void pc1715_init(pc1715 *m) {
  memset(m, 0, sizeof(*m));
  pc1715_reset(m);
}
int pc1715_load(pc1715 *m, const void *data, size_t n) {
  if (!m || !data || n != sizeof(m->rom))
    return -EINVAL;
  if (m->cpu.cycles)
    return -EBUSY;
  memcpy(m->rom, data, n);
  return 0;
}
int pc1715_attach(pc1715 *m, const pc1715_card *card) {
  if (!m)
    return -EINVAL;
  if (m->cpu.cycles)
    return -EBUSY;
  m->card = card ? *card : (pc1715_card){0};
  if (m->card.reset)
    m->card.reset(m->card.user);
  return 0;
}
void pc1715_run(pc1715 *m, unsigned ticks) {
  while (ticks--) {
    peripheral_tick(m);
    if (!m->card_offline && m->card.tick)
      m->card.tick(m->card.user, m->cpu.cycles);
    if (m->io_waiting) {
      /* The chips core exposes reads after its WAIT sampling microstep.
       * Hold the exposed transaction before its next (data consuming) step.
       * Never tick that microstep with placeholder data or repeat side effects. */
      uint16_t address = Z80_GET_ADDR(m->cpu.pins);
      m->io_waiting = 0;
      if (m->cpu.pins & Z80_RD) {
        uint8_t data = input(m, address);
        Z80_SET_DATA(m->cpu.pins, data);
      } else output(m, address, Z80_GET_DATA(m->cpu.pins));
      if (m->io_waiting) m->cpu.pins |= Z80_WAIT;
      else m->cpu.pins &= ~Z80_WAIT;
      m->wait_ticks++;
      m->cpu.cycles++;
      continue;
    }
    int irq = pc1715_irq_pending(m);
    dac_z80_tick(&m->cpu, irq, 0);
    if (!(m->cpu.pins & Z80_IORQ))
      m->io_active = 0;
    if (m->cpu.pins & Z80_RETI)
      pc1715_irq_reti(m);
  }
}
