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
  uint8_t rom[16384] = {0x3e, 0x42, 0x32, 0x00, 0x80, 0xc3, 0x00, 0x00},
          prom[256] = {0};
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
  m->bank = 1;                /* write bank remains 0 */
  m->ram[65536 + 0x4000] = 0xa5;
  assert(robotron_read(m, 0x4000) == 0xa5);
  robotron_write(m, 0x4000, 0x5a);
  assert(count == 2 && events[0].offset == 65536 + 0x4000);
  assert(events[1].offset == 0x4000 && events[1].space == DAC_SPACE_RAM);
  assert(m->ram[0x4000] == 0x5a && events[0].master == DAC_MASTER_CPU);
  m->bank = 0;
  m->rom[0] = 0x76;
  /* Program DMA through its real registers: one RAM-to-RAM byte. */
  const uint8_t dma[] = {0xc3, 0x7d, 0,    0x40, 0,    0,    0x14, 0x10, 0x9d,
                         0,    0x50, 0x12, 0x24, 0x82, 0xcf, 0xab, 0x87, 0x8a};
  for (unsigned i = 0; i < sizeof(dma); i++)
    robotron_output(m, 0, dma[i]);
  count = 0;
  robotron_run(m, 6);
  assert(count == 2 && !strcmp(events[0].kind, "MR") &&
         !strcmp(events[1].kind, "MW"));
  assert(events[0].master == DAC_MASTER_DMA &&
         events[1].master == DAC_MASTER_DMA);
  assert(events[0].offset == 0x4000 && events[1].offset == 0x5000);
  assert(m->ram[0x5000] == 0x5a && m->trace_master == DAC_MASTER_CPU);
  assert(m->cpu.bus.ack(m) == 0x24);
  assert(!strcmp(events[2].kind, "IA") && events[2].data == 0x24);
  free(m);
}
/* An original tiny ROM programs a 4x2, four-scanline display. Save before
 * and after the first visible scanline; resume through a complete frame.
 * Use the public snapshot API, not a memcpy of the machine structure. */
static void robotron_scanline_snapshots(void) {
  dac_session *s = dac_create(2), *resumed = dac_create(2);
  uint8_t rom[2048] = {0x3e, 0,    0xd3, 0x19, 0x3e, 3,    0xd3, 0x18,
                       0x3e, 1,    0xd3, 0x18, 0x3e, 3,    0xd3, 0x18,
                       0x3e, 0x70, 0xd3, 0x18, 0x3e, 0x80, 0xd3, 0x19,
                       0x3e, 255,  0xd3, 0x18, 0x3e, 0,    0xd3, 0x18,
                       0x3e, 0x20, 0xd3, 0x19, 0x76};
  uint8_t prom[256] = {0}, glyphs[4096] = {0};
  for (unsigned y = 0; y < 4; y++)
    glyphs[y * 128] = 0x80 >> y;
  assert(s && resumed);
  dac_session *sessions[] = {s, resumed};
  for (unsigned i = 0; i < 2; i++) {
    assert(!dac_load(sessions[i], 0, rom, sizeof(rom)));
    assert(!dac_load(sessions[i], 1, prom, sizeof(prom)));
    assert(!dac_load(sessions[i], 2, glyphs, sizeof(glyphs)));
    assert(!dac_power(sessions[i], 1));
  }
  unsigned n = dac_state_size(s), boundary = 0;
  void *before = malloc(n), *after = malloc(n);
  assert(before && after);
  for (unsigned t = 0; t < 1000; t++) {
    assert(!dac_state_save(s, before, n));
    assert(dac_run(s, 1) == 1);
    if (dac_video(s)[0] == 0xff83e7a0) {
      boundary = t + 1;
      break;
    }
  }
  assert(boundary && !dac_state_save(s, after, n));
  for (unsigned side = 0; side < 2; side++) {
    assert(!dac_reset(s));
    assert(dac_run(s, boundary - 1 + side) == boundary - 1 + side);
    assert(!dac_state_save(s, before, n));
    assert(!dac_state_load(resumed, before, n));
    assert(dac_video(resumed)[0] == (side ? 0xff83e7a0 : 0xff101812));
    /* Batch sizes cross different CPU/character fractions, including the
     * next scanline and retrace. Observation/rendering must not advance it. */
    for (unsigned batch = 1; batch <= 29; batch++) {
      assert(dac_run(s, batch) == batch);
      for (unsigned tick = 0; tick < batch; tick++)
        assert(dac_run(resumed, 1) == 1);
      assert(dac_width(s) == dac_width(resumed) &&
             dac_height(s) == dac_height(resumed));
      assert(!memcmp(dac_video(s), dac_video(resumed),
                     dac_width(s) * dac_height(s) * sizeof(uint32_t)));
      assert(!dac_state_save(s, before, n) &&
             !dac_state_save(resumed, after, n));
      assert(!memcmp(before, after, n));
    }
  }
  free(before);
  free(after);
  dac_destroy(s);
  dac_destroy(resumed);
}

static void robotron_dma_snapshot(void) {
  dac_session *s = dac_create(2), *copy = dac_create(2);
  uint8_t rom[2048] = {0}, prom[256] = {0};
  unsigned pos = 0;
  const uint8_t setup[] = {0xc3, 0x7d, 0,    0x40, 0,    0,
                           0x14, 0x10, 0x9d, 0,    0x50, 0x12,
                           0x24, 0x82, 0xcf, 0xab, 0x87, 0x8a};
  for (unsigned i = 0; i < sizeof(setup); i++) {
    rom[pos++] = 0x3e;
    rom[pos++] = setup[i];
    rom[pos++] = 0xd3;
    rom[pos++] = 0;
  }
  rom[pos] = 0x76;
  dac_session *both[] = {s, copy};
  for (unsigned i = 0; i < 2; i++) {
    assert(!dac_load(both[i], 0, rom, sizeof(rom)) &&
           !dac_load(both[i], 1, prom, sizeof(prom)));
    assert(!dac_power(both[i], 1));
  }
  count = 0;
  dac_trace_sink sink = {record, &count, 0, 0};
  assert(!dac_set_trace(s, &sink));
  unsigned found = 0;
  for (unsigned i = 0; i < 1000 && !found; i++) {
    count = 0;
    assert(dac_run(s, 1) == 1);
    for (unsigned j = 0; j < count; j++)
      if (events[j].master == DAC_MASTER_DMA && !strcmp(events[j].kind, "MR"))
        found = 1;
  }
  assert(found); /* Save with a byte latched but its destination not written. */
  unsigned n = dac_state_size(s);
  void *a = malloc(n), *b = malloc(n);
  assert(a && b);
  assert(!dac_state_save(s, a, n) && !dac_state_load(copy, a, n));
  for (unsigned i = 0; i < 8; i++) {
    assert(dac_run(s, 1) == 1 && dac_run(copy, 1) == 1);
    assert(!dac_state_save(s, a, n) && !dac_state_save(copy, b, n));
    assert(!memcmp(a, b, n));
  }
  free(a);
  free(b);
  dac_destroy(s);
  dac_destroy(copy);
}

static void serial_snapshots(void) {
  dac_session *s = dac_create(2), *copy = dac_create(2);
  uint8_t rom[2048] = {0}, prom[256] = {0};
  unsigned n = 0;
  const uint8_t sio[] = {3, 0xc1, 4, 0x44, 5, 0xea};
  for (unsigned i = 0; i < sizeof(sio); i++) {
    rom[n++] = 0x3e;
    rom[n++] = sio[i];
    rom[n++] = 0xd3;
    rom[n++] = 0x0f;
  }
  const uint8_t timer[] = {0x3e, 7, 0xd3, 9, 0x3e, 1, 0xd3, 9, 0x76};
  memcpy(rom + n, timer, sizeof(timer));
  dac_session *both[] = {s, copy};
  for (unsigned i = 0; i < 2; i++) {
    assert(!dac_load(both[i], 0, rom, sizeof(rom)) &&
           !dac_load(both[i], 1, prom, sizeof(prom)) && !dac_power(both[i], 1));
  }
  assert(!dac_printer_state(s, 3));
  assert(dac_printer_state(s, 4) < 0);
  assert(!dac_serial_signals(s, 3));
  assert(dac_run(s, 500) == 500);
  assert(!dac_serial_send(s, 0xa5));
  assert(dac_run(s, 1000) == 1000);
  unsigned size = dac_state_size(s);
  void *a = malloc(size), *b = malloc(size);
  assert(a && b);
  assert(!dac_state_save(s, a, size) && !dac_state_load(copy, a, size));
  assert(dac_printer_status(copy) == 3);
  for (unsigned i = 0; i < 20; i++) {
    assert(dac_run(s, 100) == 100 && dac_run(copy, 100) == 100);
    assert(!dac_state_save(s, a, size) && !dac_state_save(copy, b, size));
    assert(!memcmp(a, b, size));
  }
  uint8_t byte =
      0; /* Queues, bit phase and RX FIFO survive exact continuation. */
  assert(dac_serial_status(s) == 3 &&
         !dac_peek(s, DAC_MEMORY_RAM, 0, &byte, 1));
  assert(!dac_serial_peer(s, 1200, 0x318));
  assert(dac_serial_peer(s, 49, 0x208) < 0 &&
         dac_serial_peer(s, 1200, 0x108) < 0);
  assert(!dac_serial_send(s, 0x42));
  dac_serial_cancel(s);
  assert(!(dac_serial_status(s) >> 8));
  assert(!dac_cables(s, 3));
  assert(dac_cable_status(s) == 3);
  assert(!dac_reset(s));
  assert(dac_cable_status(s) == 3 && dac_serial_status(s) == 3);
  assert(dac_printer_status(s) == 3);
  assert(dac_serial_peer_baud(s) == 1200 && dac_serial_peer_format(s) == 0x318);
  assert(dac_video(s)[0] == 0xff101812);
  assert(!dac_cables(s, 0));
  free(a);
  free(b);
  dac_destroy(s);
  dac_destroy(copy);
}

static void bounded_timeline(void) {
  dac_session *s = dac_create(2);
  uint8_t rom[2048] = {0x3e, 0x44, 0xd3, 0x15, 0xc3, 0, 0}, prom[256] = {0};
  assert(!dac_load(s, 0, rom, sizeof(rom)) &&
         !dac_load(s, 1, prom, sizeof(prom)) && !dac_power(s, 1));
  dac_timeline_capture(s, 1);
  assert(dac_run(s, 100000) == 100000);
  assert(dac_timeline_count(s) == 512);
  const uint32_t *rows = dac_timeline_data(s);
  assert(rows[2] == 3 && (rows[3] & 255) == 0x15 && rows[4] == 0x44);
  uint32_t first = rows[0];
  assert(dac_run(s, 100000) == 100000 && rows[0] == first &&
         dac_timeline_count(s) == 512);
  dac_timeline_capture(s, 0);
  assert(!dac_timeline_count(s));
  assert(!dac_timeline_arm(s, 1, 0x16, 4, 28, 0));
  assert(dac_run(s, 10000) == 10000 && dac_timeline_status(s) == 1 &&
         dac_timeline_count(s) == 4);
  // Arm on a later port: the first four writes become the bounded pre-trigger
  // history.
  uint8_t trigger_rom[2048] = {0x3e, 0x44, 0xd3, 0x15, 0x3c, 0xfe, 0x49, 0xc2,
                               2,    0,    0xd3, 0x16, 0xc3, 0,    0};
  assert(!dac_power(s, 0) &&
         !dac_load(s, 0, trigger_rom, sizeof(trigger_rom)) && !dac_power(s, 1));
  assert(!dac_timeline_arm(s, 1, 0x16, 4, 28, 0));
  assert(dac_run(s, 100000) == 100000 && dac_timeline_status(s) == 3 &&
         dac_timeline_count(s) == 512);
  rows = dac_timeline_data(s);
  assert(dac_timeline_trigger(s) == 5);
  assert((rows[3] & 255) == 0x15 && (rows[4 * 13 + 3] & 255) == 0x16);
  assert(rows[4] == 0x45 && rows[3 * 13 + 4] == 0x48);
  assert(dac_timeline_arm(s, 6, 0, 0, 28, 0) < 0);
  assert(!dac_timeline_arm(s, 4, 0, 8, 28, 2));
  assert(dac_run(s, 10000) == 10000 && !dac_timeline_count(s));
  dac_timeline_stop(s);
  assert(!dac_timeline_status(s));
  dac_destroy(s);
}
static void debugger(void) {
  dac_session *s = dac_create(2);
  uint8_t rom[2048] = {0x3e, 0x44, 0xd3, 0x15, 0xc3, 0, 0}, prom[256] = {0};
  assert(!dac_load(s, 0, rom, sizeof(rom)) &&
         !dac_load(s, 1, prom, sizeof(prom)) && !dac_power(s, 1));
  unsigned cycles = dac_debug_reg(s, 17);
  assert(dac_debug_byte(s, 0) == 0x3e);
  assert((dac_debug_map(s, 0, 0) >> 24) == DAC_SPACE_ROM);
  assert(dac_debug_disassemble(s, 0) == 2);
  assert(strstr(dac_debug_text(s), "LD A"));
  assert(dac_debug_reg(s, 17) == cycles);
  for (unsigned i = 0; i < 3; i++) {
    assert(dac_debug_step(s) > 0);
    assert(dac_debug_reg(s, 21));
  }
  assert((dac_debug_reg(s, 2) >> 8) == 0x44);
  assert(!dac_timeline_arm(s, 1, 0x15, 8, 28, 0) && !dac_debug_break(s, 1));
  unsigned used = dac_debug_run(s, 10000);
  assert(used > 0 && used < 10000 && dac_debug_hit(s));
  assert(dac_timeline_trigger(s) > 0);
  assert(dac_debug_run(s, 100) == 0);
  assert(!dac_debug_break(s, 0) && dac_debug_run(s, 100) == 100);
  dac_destroy(s);
}
int main(void) {
  debugger();
  bounded_timeline();
  serial_snapshots();
  assert(dac_verification_abi() == 1);
  sessions(0);
  sessions(2);
  robotron_bus();
  robotron_scanline_snapshots();
  robotron_dma_snapshot();
  puts("PASS shared runtime observation, isolation, lifecycle and Robotron "
       "mapped CPU/DMA/IA traces");
}
