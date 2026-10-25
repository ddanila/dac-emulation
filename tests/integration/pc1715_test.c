#include "../../common/runtime/pc1715.h"
#include "../../common/runtime/observe.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  unsigned reads, writes, ticks, resets, acks, retis, irq;
  uint16_t address;
  uint8_t data;
} card_state;
static int card_read(void *p, uint16_t a, uint8_t *data) {
  card_state *s = p;
  s->reads++;
  s->address = a;
  *data = 0xa5;
  return (a & 255) == 2;
}
static void card_write(void *p, uint16_t a, uint8_t data) {
  card_state *s = p;
  s->writes++;
  s->address = a;
  s->data = data;
}
static void card_tick(void *p, uint64_t cycle) {
  card_state *s = p;
  assert(cycle == s->ticks++);
}
static int card_irq(void *p) { return ((card_state *)p)->irq; }
static uint8_t card_ack(void *p) {
  card_state *s = p;
  s->acks++;
  s->irq = 0;
  return 0xff;
}
static void card_reti(void *p) { ((card_state *)p)->retis++; }
static void card_reset(void *p) {
  card_state *s = p;
  unsigned resets = s->resets + 1;
  memset(s, 0, sizeof(*s));
  s->resets = resets;
}
static pc1715_card card(card_state *s) {
  return (pc1715_card){s, card_read, card_write, card_tick, card_irq,
                       card_ack, card_reti, card_reset};
}
static unsigned ir, iw, ia, mr, mw;
static void observe(void *user, const dac_trace_event *e) {
  (void)user;
  assert(e->source == 3 && e->master == DAC_MASTER_CPU);
  if (!strcmp(e->kind, "IR")) ir++;
  if (!strcmp(e->kind, "IW")) iw++;
  if (!strcmp(e->kind, "IA")) ia++;
  if (!strcmp(e->kind, "MR")) mr++;
  if (!strcmp(e->kind, "MW")) mw++;
}
static void boot_program(uint8_t *rom) {
  /* Original synthetic test: copy ROM into shadow RAM, switch overlay off,
   * consume exactly one FIFO byte, issue a write, halt. */
  const uint8_t code[] = {
    0x31, 0x00, 0xf0, 0x21, 0, 0, 0x11, 0, 0, 0x01, 0, 8, 0xed, 0xb0,
    0x3e, 0x5a, 0xd3, 0x28, 0x01, 0x02, 0x12, 0xed, 0x78,
    0x32, 0x00, 0x80, 0x3e, 0xc3, 0xd3, 0x04, 0x76};
  memset(rom, 0, 2048);
  memcpy(rom, code, sizeof(code));
}
static void board(void) {
  pc1715 *m = malloc(sizeof(*m)), *split = malloc(sizeof(*split));
  assert(m && split);
  uint8_t rom[2048];
  boot_program(rom);
  pc1715_init(m);
  assert(pc1715_load(m, rom, 2047) == -EINVAL);
  assert(!pc1715_load(m, rom, sizeof(rom)));
  pc1715_write(m, 0, 0x42);
  assert(pc1715_read(m, 0) == rom[0] && m->ram[0] == 0x42);
  pc1715_write(m, 0x800, 0x66);
  assert(pc1715_read(m, 0x800) == 0x66); /* no ROM mirroring */
  card_state s = {0}, ss = {0};
  pc1715_card c = card(&s), cs = card(&ss);
  assert(!pc1715_attach(m, &c));
  m->trace = (dac_trace_sink){observe, NULL, 0, 0};
  pc1715_run(m, 60000);
  assert(!m->rom_enabled && (m->cpu.pins & Z80_HALT));
  assert(m->ram[0x8000] == 0xa5 && s.reads == 1 && s.writes == 2);
  assert(s.address == 0xc304 && s.data == 0xc3 && s.ticks == 60000);
  assert(ir == 1 && iw == 2 && !ia && mr && mw);
  assert(pc1715_load(m, rom, sizeof(rom)) == -EBUSY);
  assert(pc1715_attach(m, NULL) == -EBUSY);
  assert(!memcmp(m->ram, rom, 2048));
  pc1715_init(split);
  assert(!pc1715_load(split, rom, sizeof(rom)) && !pc1715_attach(split, &cs));
  pc1715_write(split, 0x800, 0x66);
  for (unsigned i = 0; i < 60000; i++) pc1715_run(split, 1);
  assert(!memcmp(m->ram, split->ram, 65536));
  assert(!memcmp(&m->cpu.cpu, &split->cpu.cpu, sizeof(z80_t)));
  assert(s.reads == ss.reads && s.writes == ss.writes);
  pc1715_reset(m);
  assert(m->rom_enabled && !m->cpu.cycles && s.resets == 2);
  assert(m->ram[0x8000] == 0xa5); /* reset does not erase physical RAM */
  assert(!pc1715_attach(m, NULL));
  pc1715_run(m, 60000);
  assert(m->ram[0x8000] == 0xff && m->unclaimed_reads == 1);
  free(split);
  free(m);
}
static void interrupts(void) {
  pc1715 *m = calloc(1, sizeof(*m));
  assert(m);
  uint8_t rom[2048] = {0x31, 0x00, 0xf0, 0xed, 0x56, 0xfb, 0x76, 0x18, 0xfd};
  const uint8_t isr[] = {0x3e, 0x77, 0x32, 0x00, 0x90, 0xed, 0x4d};
  memcpy(rom + 0x38, isr, sizeof(isr));
  card_state s = {0};
  pc1715_card c = card(&s);
  pc1715_init(m);
  assert(!pc1715_load(m, rom, sizeof(rom)) && !pc1715_attach(m, &c));
  s.irq = 1;
  ir = iw = ia = 0;
  m->trace = (dac_trace_sink){observe, NULL, 0, 0};
  pc1715_run(m, 1000);
  assert(m->ram[0x9000] == 0x77 && s.acks == 1 && s.retis == 1);
  assert(ia == 1 && !ir && !iw && !s.reads && !s.writes);
  free(m);
}
static void runtime(void) {
  uint8_t rom[2048], data = 0;
  boot_program(rom);
  dac_session *s = dac_create(3), *wm = dac_create(2);
  assert(s && wm && !dac_create(4));
  assert(dac_power(s, 1) == -ENOENT);
  assert(dac_load(s, 1, rom, 256) == -EINVAL);
  assert(!dac_load(s, 0, rom, sizeof(rom)));
  card_state state = {0};
  pc1715_card c = card(&state);
  assert(dac_pc1715_attach(wm, &c) == -ENOTSUP);
  assert(!dac_pc1715_attach(s, &c));
  assert(!dac_power(s, 1)); /* no W/M CAS PROM required */
  assert(dac_pc1715_attach(s, NULL) == -EBUSY);
  ir = iw = ia = mr = mw = 0;
  dac_trace_sink sink = {observe, NULL, 0, 0};
  assert(!dac_set_trace(s, &sink) && dac_run(s, 60000) == 60000);
  assert(ir == 1 && iw == 2 && mr && mw);
  dac_observation result;
  assert(!dac_observe(s, &result) && result.cycles == 60000 && !result.bank && result.halted);
  assert(!dac_peek(s, DAC_MEMORY_RAM, 0x8000, &data, 1) && data == 0xa5);
  assert(dac_peek(s, DAC_MEMORY_RAM, 65536, &data, 1) == -EINVAL);
  assert(dac_peek(s, DAC_MEMORY_ROM, 2048, &data, 1) == -EINVAL);
  assert(dac_peek(s, DAC_MEMORY_VIDEO, 0, &data, 1) == -ENOTSUP);
  assert(!dac_video(s) && !dac_width(s) && !dac_height(s));
  assert(dac_mount_unit(s, 0, rom, sizeof(rom), 0) == -ENOTSUP);
  assert(dac_key(s, 'A', 1) == -ENOTSUP);
  assert(!dac_state_size(s) && dac_state_save(s, rom, sizeof(rom)) == -ENOTSUP);
  assert(dac_state_load(s, rom, sizeof(rom)) == -ENOTSUP);
  assert(!dac_reset(s) && state.resets == 2);
  assert(!dac_observe(s, &result) && result.cycles == 0 && result.bank == 1);
  assert(dac_run(s, 60000) == 60000 && state.reads == 1);
  assert(!dac_power(s, 0) && !dac_pc1715_attach(s, NULL));
  assert(!dac_power(s, 1) && dac_run(s, 60000) == 60000);
  assert(!dac_peek(s, DAC_MEMORY_RAM, 0x8000, &data, 1) && data == 0xff);
  dac_destroy(s);
  dac_destroy(wm);
}
int main(void) {
  board();
  interrupts();
  runtime();
  puts("PASS plain PC1715 memory, bus transactions, IRQ/RETI and session isolation");
  return 0;
}
