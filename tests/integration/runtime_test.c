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

typedef struct {
  uint64_t hash;
  unsigned dma_read, dma_write, ack, key, serial, lower_a, upper_a, ctrl_prefix, combined_prefix;
} mixed_trace;
static void mixed_record(void *user, const dac_trace_event *e) {
  mixed_trace *t = user;
  t->hash = t->hash * 1099511628211ull ^ e->cycle ^
            ((uint64_t)e->address << 32) ^ ((uint64_t)e->data << 20) ^
            ((uint64_t)e->master << 16) ^ ((unsigned char)e->kind[0] << 8) ^
            (unsigned char)e->kind[1];
  t->dma_read += e->master == DAC_MASTER_DMA && !strcmp(e->kind, "MR");
  t->dma_write += e->master == DAC_MASTER_DMA && !strcmp(e->kind, "MW");
  t->ack += !strcmp(e->kind, "IA");
  t->key +=
      !strcmp(e->kind, "IR") && (e->address & 255) == 12 && e->data == 'K';
  t->lower_a += !strcmp(e->kind,"IR") && (e->address&255)==12 && e->data=='a';
  t->upper_a += !strcmp(e->kind,"IR") && (e->address&255)==12 && e->data=='A';
  t->combined_prefix += !strcmp(e->kind,"IR") && (e->address&255)==12 && e->data==0xe3;
  t->ctrl_prefix += !strcmp(e->kind,"IR") && (e->address&255)==12 && e->data==0xe1;
  t->serial +=
      !strcmp(e->kind, "IR") && (e->address & 255) == 13 && e->data == 0xa5;
}
static void emit_out(uint8_t *rom, unsigned *p, unsigned port, unsigned value) {
  rom[(*p)++] = 0x3e;
  rom[(*p)++] = value;
  rom[(*p)++] = 0xd3;
  rom[(*p)++] = port;
}
/* Original bounded workload, no historical ROM/OS or HDL. DMA steals cycles
 * while seek, serial input/output, keyboard polling and interrupt service run.
 * Snapshots compare both complete state and bus transcripts across slice sizes.
 */
static void mixed_workload_snapshots(int firmware_keyboard) {
  uint8_t keyboard[2048]={0};
  if(firmware_keyboard){
    /* Original ROM: scan column 0, light both LEDs, clock K into SIO A,
     * then wait for physical release and extinguish both LEDs. No RAM needed. */
    const uint8_t scan[]={0x01,0x01,0x80,0xed,0x78,0xe6,1,0x28,0xfa,
                          0x06,100,0x10,0xfe, /* allow host SIO setup */
                          0x01,0x00,0x60,0xed,0x78};
    memcpy(keyboard,scan,sizeof(scan));unsigned k=sizeof(scan);
    emit_out(keyboard,&k,0,0);
    for(unsigned bit=0;bit<8;bit++)emit_out(keyboard,&k,0,('K'>>bit)&1);
    emit_out(keyboard,&k,0,1);
    const uint8_t lamps[]={0x01,0,0x60,0xed,0x78};
    memcpy(keyboard+k,lamps,sizeof(lamps));k+=sizeof(lamps);
    /* A15 enables matrix input; A14/A13 must remain high to keep lamps on. */
    const uint8_t release[]={0x01,0x01,0xe0,0xed,0x78,0xe6,1,0x20,0xfa,
                             0x01,0,0,0xed,0x78,0x76};
    memcpy(keyboard+k,release,sizeof(release));
  }
  uint8_t rom[2048] = {0xc3, 0, 1}, prom[256] = {0}, disk[819200] = {0};
  const uint8_t handler[] = {0xf5, 0xdb, 12, 0xdb, 13,   0x3e, 0x28, 0xd3,
                             14,   0xd3, 15, 0xf1, 0xfb, 0xed, 0x4d};
  memcpy(rom + 0x38, handler, sizeof(handler));
  unsigned p = 256;
  rom[p++] = 0x31;
  rom[p++] = 0;
  rom[p++] = 0xc0; /* SP */
  rom[p++] = 0xed;
  rom[p++] = 0x56; /* IM 1 */
  for (unsigned i = 0; i < 32; i++) {
    rom[p++] = 0x3e;
    rom[p++] = i + 1;
    rom[p++] = 0x32;
    rom[p++] = i;
    rom[p++] = 0x40;
  }
  const uint8_t sio[] = {3, 0xc1, 4, 0x44, 5, 0x68, 1, 0x12};
  for (unsigned ch = 0; ch < 2; ch++)
    for (unsigned i = 0; i < sizeof(sio); i++)
      emit_out(rom, &p, 14 + ch, firmware_keyboard && ch==0 && i==3 ? 4 : sio[i]);
  for (unsigned port = 8; port < 10; port++) {
    emit_out(rom, &p, port, 7);
    emit_out(rom, &p, port, 1);
  }
  emit_out(rom, &p, 12, 'P');
  emit_out(rom, &p, 13, 'S');
  const uint8_t seek[] = {15, 0, 2};
  for (unsigned i = 0; i < sizeof(seek); i++)
    emit_out(rom, &p, 0x1d, seek[i]);
  const uint8_t dma[] = {0xc3, 0x7d, 0,    0x40, 31,   0,    0x14, 0x10, 0x9d,
                         0,    0x50, 0x12, 0x24, 0x82, 0xcf, 0xab, 0x87, 0x8a};
  for (unsigned i = 0; i < sizeof(dma); i++)
    emit_out(rom, &p, 0, dma[i]);
  rom[p++] = 0xfb;
  unsigned loop = p;
  rom[p++] = 0xdb;
  rom[p++] = 12;
  rom[p++] = 0xdb;
  rom[p++] = 13;
  rom[p++] = 0xc3;
  rom[p++] = loop;
  rom[p++] = loop >> 8;
  assert(p < sizeof(rom));
  dac_session *s = dac_create(2), *copy = dac_create(2), *both[] = {s, copy};
  for (unsigned i = 0; i < 2; i++) {
    assert(!dac_load(both[i], 0, rom, sizeof(rom)) &&
           !dac_load(both[i], 1, prom, sizeof(prom)));
    if(firmware_keyboard)assert(!dac_load(both[i],3,keyboard,sizeof(keyboard)));
    assert(!dac_mount(both[i], disk, sizeof(disk), 1) &&
           !dac_power(both[i], 1));
  }
  mixed_trace ta = {0}, tb = {0};
  dac_trace_sink sa = {mixed_record, &ta, 0, 0}, sb = {mixed_record, &tb, 0, 0};
  assert(!dac_set_trace(s, &sa) && !dac_set_trace(copy, &sb));
  assert(!dac_serial_signals(s, 3) && !dac_serial_send(s, 0xa5) &&
         !(firmware_keyboard ? dac_matrix(s,0,1) : dac_key(s, 'K', 1)));
  for (unsigned i = 0; i < 10000 && !ta.dma_read; i++)
    assert(dac_run(s, 1) == 1);
  assert(ta.dma_read == 1 && !ta.dma_write); /* latched source, pending write */
  unsigned size = dac_state_size(s);
  void *a = malloc(size), *b = malloc(size);
  assert(a && b);
  assert(!dac_state_save(s, a, size) && !dac_state_load(copy, a, size));
  unsigned seen_key = ta.key, seen_serial = ta.serial, seen_ack = ta.ack;
  const unsigned slices[] = {1, 2, 7, 128, 3000, 50000};
  for (unsigned n = 0; n < sizeof(slices) / sizeof(*slices); n++) {
    ta = (mixed_trace){0};
    tb = (mixed_trace){0};
    assert(dac_run(s, slices[n]) == slices[n]);
    for (unsigned i = 0; i < slices[n]; i++)
      assert(dac_run(copy, 1) == 1);
    assert(!memcmp(&ta, &tb, sizeof(ta)));
    seen_key += ta.key;
    seen_serial += ta.serial;
    seen_ack += ta.ack;
    assert(!dac_state_save(s, a, size) && !dac_state_save(copy, b, size));
    assert(!memcmp(a, b, size));
    assert(!dac_state_load(copy, a, size)); /* rebind at each mixed boundary */
  }
  uint8_t bytes[32];
  assert(!dac_peek(s, DAC_MEMORY_RAM, 0x5000, bytes, sizeof(bytes)));
  for (unsigned i = 0; i < 32; i++)
    assert(bytes[i] == i + 1);
  assert(seen_key && seen_serial && seen_ack);
  assert(dac_drive_steps_unit(s, 0) == 2);
  assert(dac_printer_size(s) == 1 && dac_printer_data(s)[0] == 'P');
  assert(dac_serial_size(s) == 1 && dac_serial_data(s)[0] == 'S');
  if(firmware_keyboard){
    assert(dac_keyboard_leds(s)==3 && dac_keyboard_leds(copy)==3);
    assert(!dac_matrix(s,0,0) && !dac_matrix(copy,0,0));
    assert(dac_run(s,2000)==2000);
    for(unsigned i=0;i<2000;i++)assert(dac_run(copy,1)==1);
    assert(!dac_keyboard_latches(s) && !dac_keyboard_latches(copy));
    assert(dac_keyboard_leds(s)==3 && dac_keyboard_leds(copy)==3);
    assert(dac_run(s,8000)==8000);
    for(unsigned i=0;i<8000;i++)assert(dac_run(copy,1)==1);
    assert(!dac_keyboard_leds(s) && !dac_keyboard_leds(copy));
    assert(!dac_state_save(s,a,size) && !dac_state_save(copy,b,size));
    assert(!memcmp(a,b,size));
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
/* Optional production snapshot qualification using externally supplied S600.
 * Main CPU repeatedly copies DMA data while polling keyboard/V24 and printing.
 * Historical firmware is deliberately absent from ordinary CI. */
/* Each window starts with a production snapshot and compares batched versus
 * one-clock scheduling, including all peripheral queues and bus events. */
static mixed_trace s600_window(dac_session *a,dac_session *b,void *left,void *right,unsigned size,mixed_trace *ta,mixed_trace *tb,unsigned clocks){
  assert(!dac_state_save(a,left,size)&&!dac_state_load(b,left,size));
  *ta=(mixed_trace){0};*tb=(mixed_trace){0};
  for(unsigned remaining=clocks;remaining;){unsigned n=remaining>100000?100000:remaining;assert(dac_run(a,n)==n);remaining-=n;}
  for(unsigned i=0;i<clocks;i++)assert(dac_run(b,1)==1);
  assert(!memcmp(ta,tb,sizeof(*ta)));
  assert(!dac_state_save(a,left,size)&&!dac_state_save(b,right,size)&&!memcmp(left,right,size));
  return *ta;
}
static void s600_workload(const uint8_t *keyboard) {
  uint8_t rom[2048]={0xc3,0,1},prom[256]={0};unsigned p=256;
  const uint8_t sio[]={3,0xc1,4,4,5,0x68};
  for(unsigned ch=0;ch<2;ch++)for(unsigned i=0;i<sizeof(sio);i++)
    emit_out(rom,&p,14+ch,ch==1&&i==3?0x44:sio[i]);
  for(unsigned port=8;port<10;port++){emit_out(rom,&p,port,7);emit_out(rom,&p,port,1);}
  unsigned loop=p;
  const uint8_t dma[]={0xc3,0x7d,0,0x40,31,0,0x14,0x10,0x9d,0,0x50,0x12,0x24,0x82,0xcf,0xab,0x87,0x8a};
  for(unsigned i=0;i<sizeof(dma);i++)emit_out(rom,&p,0,dma[i]);
  emit_out(rom,&p,12,'P');emit_out(rom,&p,13,'S');
  rom[p++]=0xdb;rom[p++]=12;rom[p++]=0xdb;rom[p++]=13;
  rom[p++]=0xc3;rom[p++]=loop;rom[p++]=loop>>8;
  dac_session *a=dac_create(2),*b=dac_create(2),*both[]={a,b};
  for(unsigned i=0;i<2;i++){assert(!dac_load(both[i],0,rom,sizeof(rom)));assert(!dac_load(both[i],1,prom,sizeof(prom)));assert(!dac_load(both[i],3,keyboard,2048));assert(!dac_power(both[i],1));}
  for(unsigned i=0;i<10;i++)assert(dac_run(a,100000)==100000);
  unsigned size=dac_state_size(a);void *left=malloc(size),*right=malloc(size);assert(left&&right);
  assert(!dac_state_save(a,left,size)&&!dac_state_load(b,left,size));
  mixed_trace ta={0},tb={0};dac_trace_sink sa={mixed_record,&ta,0,0},sb={mixed_record,&tb,0,0};assert(!dac_set_trace(a,&sa)&&!dac_set_trace(b,&sb));
  /* Hold/release A; Shift+A; Ctrl; Caps then SI/SO latches. */
  const unsigned inputs[][3]={{61,1,0},{61,0,0},{65,1,0},{61,1,0},{61,0,0},{65,0,0},{64,1,0},{61,1,0},{61,0,0},{64,0,0},{71,1,1},{71,0,1},{69,1,3},{69,0,3},{71,1,2},{71,0,2},{69,1,0},{69,0,0}};
  unsigned dma_reads=0,serial_reads=0,lower=0,upper=0,ctrl=0;
  for(unsigned n=0;n<sizeof(inputs)/sizeof(*inputs);n++){
    assert(!dac_matrix(a,inputs[n][0],inputs[n][1])&&!dac_matrix(b,inputs[n][0],inputs[n][1]));
    assert(!dac_serial_signals(a,3)&&!dac_serial_signals(b,3));assert(!dac_serial_send(a,0xa5)&&!dac_serial_send(b,0xa5));
    /* Snapshot just after the edge, before the keyboard has scanned it. */
    assert(!dac_state_save(a,left,size)&&!dac_state_load(b,left,size));
    ta=(mixed_trace){0};tb=(mixed_trace){0};for(unsigned i=0;i<4;i++)assert(dac_run(a,100000)==100000);
    for(unsigned i=0;i<400000;i++)assert(dac_run(b,1)==1);
    assert(!memcmp(&ta,&tb,sizeof(ta)));dma_reads+=ta.dma_read;serial_reads+=ta.serial;lower+=ta.lower_a;upper+=ta.upper_a;ctrl+=ta.ctrl_prefix;
    /* A held key can still be in the S600 scan/debounce path. Qualify mode
     * latches after release, as the standalone historical-ROM fixture does. */
    assert(dac_keyboard_leds(a)==dac_keyboard_leds(b));
    if(!inputs[n][1])assert(dac_keyboard_leds(a)==inputs[n][2]);
    assert(!dac_state_save(a,left,size)&&!dac_state_save(b,right,size)&&!memcmp(left,right,size));
  }
  assert(dma_reads&&serial_reads&&lower&&upper&&ctrl&&dac_printer_size(a)&&dac_serial_size(a));
  /* Shift+Ctrl overlap; release Shift first while Ctrl remains held. */
  const unsigned overlap[][2]={{65,1},{64,1},{61,1},{61,0},{65,0},{61,1},{61,0},{64,0}};
  unsigned combined=0;
  for(unsigned i=0;i<sizeof(overlap)/sizeof(*overlap);i++){
    assert(!dac_matrix(a,overlap[i][0],overlap[i][1]));
    mixed_trace t=s600_window(a,b,left,right,size,&ta,&tb,400000);combined+=t.combined_prefix;
  }
  assert(combined);
  /* Find an actual partially shifted keyboard byte, not an arbitrary delay.
   * This optional native fixture deliberately inspects snapshot layout 16. */
  assert(!dac_matrix(a,61,1));unsigned found=0;
  for(unsigned n=0;n<1600;n++){
    assert(dac_run(a,256)==256);assert(!dac_state_save(a,left,size));
    uint32_t header[8];memcpy(header,left,sizeof(header));assert(header[1]==16);
    robotron_sio_rx rx;memcpy(&rx,(uint8_t*)left+sizeof(header)+offsetof(robotron,rx),sizeof(rx));
    if(rx.phase&&rx.bits>0&&rx.bits<8){found=1;break;}
  }
  assert(found);
  mixed_trace partial=s600_window(a,b,left,right,size,&ta,&tb,400000);assert(partial.lower_a);
  /* REP acts on the held A contact. Verify repetition and its clean stop. */
  assert(!dac_matrix(a,70,1));
  mixed_trace repeat=s600_window(a,b,left,right,size,&ta,&tb,8000000);assert(repeat.lower_a>=2&&repeat.dma_read&&dac_printer_size(a)&&dac_serial_size(a));
  assert(!dac_matrix(a,70,0));s600_window(a,b,left,right,size,&ta,&tb,400000);
  mixed_trace stopped=s600_window(a,b,left,right,size,&ta,&tb,1000000);assert(!stopped.lower_a);
  /* Runtime reset releases physical input state. Firmware restarts cleanly;
   * a subsequent real press must still work with DMA and serial active. */
  assert(!dac_reset(a)&&!dac_reset(b));
  s600_window(a,b,left,right,size,&ta,&tb,1000000);
  assert(!dac_matrix(a,61,0));s600_window(a,b,left,right,size,&ta,&tb,400000);
  assert(!dac_matrix(a,61,1));assert(!dac_serial_send(a,0xa5));
  mixed_trace fresh=s600_window(a,b,left,right,size,&ta,&tb,400000);assert(fresh.lower_a&&fresh.serial&&fresh.dma_read);
  assert(!dac_matrix(a,61,0));s600_window(a,b,left,right,size,&ta,&tb,400000);
  free(left);free(right);dac_destroy(a);dac_destroy(b);
  puts("PASS optional S600 mixed snapshots: 18 matrix/LED boundaries, DMA, printer and V24; overlap, in-flight keyboard RX, REP stop and held-key reset; <24M clocks per instance");
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
  assert(!dac_debug_target(s, 2));
  used = dac_debug_run(s, 10000);
  assert(used && used < 10000 && dac_debug_hit(s) == 2);
  assert(dac_debug_reg(s, 21) && dac_debug_reg(s, 22) == 2);
  assert(dac_debug_run(s, 100) == 0);
  assert(dac_debug_target(s, 65536) < 0);
  assert(!dac_debug_break(s, 0) && dac_debug_run(s, 10) == 10);
  dac_destroy(s);
}
int main(int argc,char **argv) {
  if(argc==3&&!strcmp(argv[1],"--s600")){uint8_t rom[2048];FILE *f=fopen(argv[2],"rb");assert(f&&fread(rom,1,sizeof(rom),f)==sizeof(rom)&&fgetc(f)==EOF);fclose(f);s600_workload(rom);return 0;}
  if(argc!=1){fprintf(stderr,"usage: runtime-test [--s600 path/to/S600.bin]\n");return 2;}

  mixed_workload_snapshots(0);
  mixed_workload_snapshots(1);
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
