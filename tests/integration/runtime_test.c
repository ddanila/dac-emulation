#include "../../common/runtime/observe.h"
#include "../../machines/robotron1715m/robotron.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static dac_trace_event events[4096];
static unsigned count;
static void record(void *user, const dac_trace_event *event) {
  assert(user == &count && count < 4096);
  events[count++] = *event;
}
static void sessions(unsigned kind) {
  dac_session *s = dac_create(kind), *other = dac_create(kind);
  uint8_t rom[16384] = {0x3e, 0x42, 0x32, 0x00, 0x80, 0xc3, 0x00, 0x00}, prom[256] = {0};
  assert(s && other);
  assert(dac_observe(s, NULL) == -EINVAL);
  size_t size = kind == 2 ? 2048 : 16384;
  assert(!dac_load(s, 0, rom, size) && !dac_load(other, 0, rom, size));
  if (kind == 2) {
    assert(!dac_load(s, 1, prom, sizeof(prom)));
    assert(!dac_load(other, 1, prom, sizeof(prom)));
  }
  assert(!dac_power(s, 1) && !dac_power(other, 1));
  count = 0;
  dac_trace_sink sink = {record, &count, 0, 0};
  assert(!dac_set_trace(s, &sink));
  assert(dac_run(s, 100) >= 100 && count > 0);
  uint8_t byte;
  dac_observation before, after;
  assert(!dac_observe(s, &before));
  unsigned recorded = count;
  assert(!dac_peek(s, DAC_MEMORY_RAM, 0x8000, &byte, 1) && byte == 0x42);
  assert(!dac_peek(other, DAC_MEMORY_RAM, 0x8000, &byte, 1) && byte == 0);
  assert(dac_peek(s, DAC_MEMORY_RAM, UINT32_MAX, &byte, 1) == -EINVAL);
  assert(dac_peek(s, 999, 0, &byte, 1) == -ENOTSUP);
  assert(!dac_observe(s, &after) && !memcmp(&before, &after, sizeof(before)));
  assert(count == recorded);
  unsigned n = dac_state_size(s);
  void *state = malloc(n);
  assert(state && !dac_state_save(s, state, n));
  assert(!dac_reset(s));
  assert(!dac_peek(s, DAC_MEMORY_RAM, 0x8000, &byte, 1) && byte == 0);
  assert(dac_run(s, 100) >= 100 && count > recorded);
  recorded = count;
  assert(!dac_state_load(s, state, n));
  assert(!dac_observe(s, &after) && after.cycles == before.cycles);
  /* Reloading a running snapshot must preserve the live host observer. */
  assert(dac_run(s, 100) >= 100 && count > recorded);
  recorded = count;
  assert(!dac_set_trace(s, NULL));
  assert(!dac_reset(s) && dac_run(s, 100) >= 100 && count == recorded);
  dac_destroy(s);
  assert(dac_run(other, 100) >= 100);
  dac_destroy(other);
  free(state);
}
static void robotron_bus(void) {
  robotron *m = malloc(sizeof(*m));
  assert(m);
  robotron_init(m);
  count = 0;
  m->trace = (dac_trace_sink){record, &count, 0, 0};
  m->prom[128 + 16 + 4] = 13; /* read bank 1 maps to physical bank 1 */
  m->bank = 1; /* write bank remains 0 */
  m->ram[65536 + 0x4000] = 0xa5;
  assert(robotron_read(m, 0x4000) == 0xa5);
  robotron_write(m, 0x4000, 0x5a);
  assert(count == 2 && events[0].offset == 65536 + 0x4000);
  assert(events[1].offset == 0x4000 && events[1].space == DAC_SPACE_RAM);
  assert(m->ram[0x4000] == 0x5a && events[0].master == DAC_MASTER_CPU);
  m->bank = 0;
  m->rom[0] = 0x76;
  /* Program DMA through its real registers: one RAM-to-RAM byte. */
  const uint8_t dma[] = {0xc3,0x7d,0,0x40,0,0,0x14,0x10,0x9d,0,0x50,0x12,
                        0x24,0x82,0xcf,0xab,0x87,0x8a};
  for (unsigned i = 0; i < sizeof(dma); i++) robotron_output(m, 0, dma[i]);
  count = 0;
  robotron_run(m, 1);
  assert(count == 2 && !strcmp(events[0].kind, "MR") && !strcmp(events[1].kind, "MW"));
  assert(events[0].master == DAC_MASTER_DMA && events[1].master == DAC_MASTER_DMA);
  assert(events[0].offset == 0x4000 && events[1].offset == 0x5000);
  assert(m->ram[0x5000] == 0x5a && m->trace_master == DAC_MASTER_CPU);
  assert(m->cpu.bus.ack(m) == 0x24);
  assert(!strcmp(events[2].kind, "IA") && events[2].data == 0x24);
  free(m);
}
int main(void) {
  assert(dac_verification_abi() == 1);
  sessions(0); sessions(2); robotron_bus();
  puts("PASS shared runtime observation, isolation, lifecycle and Robotron mapped CPU/DMA/IA traces");
}
