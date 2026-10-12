#include "../../machines/robotron1715m/robotron.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static robotron m;
static uint8_t disk[819200];
static uint32_t pixels[640 * 384];
static void send(unsigned port, const uint8_t *p, unsigned n) {
  while (n--)
    robotron_output(&m, port, *p++);
}
static void init(void) {
  robotron_init(&m);
  m.rom[0] = 0x76; /* HALT */
  memset(disk, 0x5a, sizeof(disk));
  assert(!robotron_disk(&m, dac_memory_storage(disk, sizeof(disk), 1), 1));
  /* Peripheral fixtures start with pre-spun, loaded drives. Startup is tested
   * separately. */
  for (unsigned u = 0; u < 2; u++) {
    m.drive[u].speed = ROBOTRON_SPINUP_TICKS;
    m.drive[u].ready = m.drive[u].loaded = 1;
    m.drive[u].ready_indexes = 2;
    m.drive[u].unload_at = UINT64_MAX;
  }
}
static void dma(unsigned a, unsigned b, unsigned n, unsigned bmode,
                unsigned ctrl) {
  const uint8_t p[] = {0xc3, 0x7d,  a,    a >> 8, n - 1,  (n - 1) >> 8,
                       0x14, bmode, 0x9d, b,      b >> 8, ctrl,
                       0x24, 0x82,  0xcf, 0xab};
  send(0, p, sizeof(p));
}
static void fdc(unsigned op) {
  const uint8_t p[] = {op, 0, 0, 0, 1, 3, 5, 0x1b, 1};
  send(0x1d, p, sizeof(p));
  robotron_run(&m, 1);
}
static void dma_memory(void) {
  init();
  for (unsigned i = 0; i < 8; i++)
    m.ram[0x4000 + i] = (uint8_t)(0x20 + i);
  dma(0x4000, 0x5000, 8, 0x10, 0x12);
  robotron_output(&m, 0, 0x87);
  robotron_run(&m, 40);
  assert(m.dma.remaining == 8); /* inactive RDY */
  robotron_output(&m, 0, 0x8a); /* WR5 active high: inverted DRQ is high */
  robotron_run(&m, 8);
  assert(!memcmp(m.ram + 0x4000, m.ram + 0x5000, 8));
  assert(m.dma.irq && !m.dma.enabled && !m.dma.remaining);
  assert(m.cpu.bus.ack(&m) == 0x24);
  assert(m.dma.in_service && !m.dma.irq);
  robotron_output(&m, 0, 0xa3);
  assert(!m.dma.in_service);
  const uint8_t mask[] = {0xbb, 0x7e};
  send(0, mask, 2);
  const uint8_t expected[] = {8, 0, 8, 0x40, 8, 0x50};
  for (unsigned i = 0; i < 6; i++)
    assert(robotron_input(&m, 0) == expected[i]);
  for (unsigned i = 0; i < 600; i++)
    assert(robotron_input(&m, 0) == expected[i % 6]);
  robotron_output(&m, 0, 0xa7); /* restart selected read sequence */
  assert(robotron_input(&m, 0) == 8);

  /* Interrupt enable alone must not generate an end-of-block interrupt. */
  dma(0x4000, 0x5000, 8, 0x10, 0x10);
  robotron_output(&m, 0, 0xb3);
  robotron_output(&m, 0, 0x87);
  robotron_run(&m, 8);
  assert(!m.dma.irq && !m.dma.remaining);
}
static void floppy_completion(void) {
  init();
  fdc(0x45);
  assert(!(robotron_input(&m, 0x1c) & 128)); /* execution delay */
  dma(0x4000, 0x41, 1024, 0x28, 0x12);
  memset(m.ram + 0x4000, 0xa5, 1024);
  robotron_output(&m, 0x20, 0xc0); /* reset released, TC gated on */
  robotron_output(&m, 0, 0x87);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles) + 1024 * 128);
  assert(m.disk_writes == 1 && m.fdc.phase == 1 && m.dma.irq);
  for (unsigned i = 0; i < 1024; i++)
    assert(disk[i] == 0xa5);
  assert(disk[1024] == 0x5a); /* no next-sector transfer */
  const uint8_t result[] = {0, 0, 0, 0, 0, 2, 3};
  for (unsigned i = 0; i < 7; i++)
    assert(robotron_input(&m, 0x1d) == result[i]);
  assert(robotron_input(&m, 0x1c) == 0x80);

  /* TC partway through a write pads its remainder, then reports next ID. */
  init();
  fdc(0x45);
  dma(0x4000, 0x41, 128, 0x28, 0x12);
  memset(m.ram + 0x4000, 0x31, 128);
  robotron_output(&m, 0x20, 0xc0);
  robotron_output(&m, 0, 0x87);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles) + 1024 * 128 + 1);
  assert(m.disk_writes == 1);
  for (unsigned i = 0; i < 1024; i++)
    assert(disk[i] == (i < 128 ? 0x31 : 0));
  for (unsigned i = 0; i < 7; i++)
    assert(robotron_input(&m, 0x1d) == result[i]);

  /* Without DMA INT, its byte counter alone cannot terminate the FDC. */
  init();
  fdc(0x45);
  dma(0x4000, 0x41, 128, 0x28, 0x10);
  robotron_output(&m, 0x20, 0xc0);
  robotron_output(&m, 0, 0x87);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles) + 128 * 128);
  assert(m.fdc.phase == 2 && !m.disk_writes && !m.dma.irq);
  robotron_output(&m, 0x20, 0x80); /* assert FDC reset */
  assert(!m.fdc.phase && robotron_input(&m, 0x1c) == 0);
  fdc(0x46);
  assert(!m.fdc.phase && !m.fdc.cmd_pos);
  robotron_output(&m, 0x20, 0xc0);
  assert(robotron_input(&m, 0x1c) == 128);
}
static void interrupt_chain(void) {
  init();
  m.dma.irq = 1;
  m.dma.irq_vector = 0x24;
  m.ctc_vector[0] = 0x80;
  m.ctc[2].pending = 1;
  m.ctc[4].pending = 1;
  assert(m.cpu.bus.ack(&m) == 0x24);
  assert(m.cpu.bus.ack(&m) == 0xff); /* DMA in service blocks CTC */
  /* Real RETI instruction must release the daisy chain. */
  m.rom[0] = 0xed;
  m.rom[1] = 0x4d;
  robotron_run(&m, 12);
  assert(!m.dma.in_service);
  assert(m.cpu.bus.ack(&m) == 0x84);
  m.ctc[3].pending = 1;
  assert(m.cpu.bus.ack(&m) == 0xff);
  m.ctc[0].pending = 1; /* higher CTC channel can preempt */
  assert(m.cpu.bus.ack(&m) == 0x80);
  robotron_output(&m, 4, 3); /* reset channel 0 */
  assert(m.cpu.bus.ack(&m) == 0xff);
  robotron_output(&m, 6, 3);
  assert(m.cpu.bus.ack(&m) == 0x86);
  robotron_output(&m, 7, 3);
  assert(m.cpu.bus.ack(&m) == 0xff); /* disconnected CTC0 ignored */
}
static void timer_cascade(void) {
  init();
  robotron_output(&m, 4, 8); /* CTC2 vector */
  robotron_output(&m, 5, 7);
  robotron_output(&m, 5, 2); /* timer: 16*2 */
  robotron_output(&m, 6, 0xc7);
  robotron_output(&m, 6, 3); /* counter: 3 pulses */
  robotron_run(&m, 95);
  assert(!m.ctc[2].pending);
  robotron_run(&m, 1);
  assert(m.ctc[2].pending);
  assert(m.cpu.bus.ack(&m) == 12);
  robotron_output(&m, 5, 3); /* reset feeding timer */
  robotron_output(&m, 6, 3);
  robotron_run(&m, 200);
  assert(!m.ctc[2].pending);
}
static void display(void) {
  init();
  unsigned w, h;
  const uint8_t parameters[] = {3, 0, 0x12, 0x70}; /* 4 cols, 1 row, 3 lines */
  robotron_output(&m, 0x19, 0);
  send(0x18, parameters, 4);
  m.vram[0] = 'A';
  m.vram[1] = 0x94; /* reverse + glyph bank 1 */
  m.vram[2] = 'B';
  m.vram[3] = 'A';
  m.chargen['A'] = 0x80;
  m.chargen[2048 + 'B'] = 0x40;
  robotron_video(&m, pixels, &w, &h);
  assert(w == 32 && h == 3);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
  robotron_output(&m, 0x19, 0x20);
  assert(robotron_input(&m, 0x19) == 0x44);
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[1] == 0xff101812);
  assert(pixels[8] == 0xff101812); /* visible attribute is blank */
  assert(pixels[16] == 0xff83e7a0 && pixels[17] == 0xff101812);
  robotron_output(&m, 0x19, 0x80);
  const uint8_t cursor[] = {0, 0};
  send(0x18, cursor, 2);
  robotron_video(&m, pixels, &w, &h);
  for (unsigned x = 0; x < 8; x++)
    assert(pixels[w + x] == 0xff83e7a0);
  assert(m.crtc[0] == 3 &&
         m.crtc[2] == 0x12); /* cursor cannot overwrite geometry */
  // Character-attribute code suppresses the upper glyph region via VSP,
  // without leaking the preceding field's reverse/highlight state.
  m.cursor[0] = 255;
  m.vram[0] = 0xc0;
  for (unsigned y = 0; y < 3; y++)
    m.chargen[y * 128 + 0x40] = 0x80;
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff101812 && pixels[w] == 0xff83e7a0 &&
         pixels[2 * w] == 0xff83e7a0);
  robotron_output(&m, 0x19, 0x40);
  robotron_video(&m, pixels, &w, &h);
  assert(robotron_input(&m, 0x19) == 0x40);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
}
static void serial_byte(unsigned value, unsigned stop) {
  robotron_serial_clock(&m, 0);
  for (unsigned i = 0; i < 8; i++)
    robotron_serial_clock(&m, (value >> i) & 1);
  robotron_serial_clock(&m, stop);
}
static void keyboard_serial(void) {
  init();
  m.keyboard_enabled = 1;
  robotron_output(&m, 0x0e, 3);
  robotron_output(&m, 0x0e, 0xc1);
  robotron_output(&m, 0x0e, 4);
  robotron_output(&m, 0x0e, 4);
  robotron_output(&m, 0x0e, 1);
  robotron_output(&m, 0x0e, 0x10);
  serial_byte(0xe0, 1);
  serial_byte(0x61, 1);
  assert(robotron_input(&m, 0x0e) & 1);
  assert(m.rx.pending);
  m.sio_regs[1][2] = 0x80;
  m.sio_regs[1][1] = 4;
  assert(m.cpu.bus.ack(&m) == 0x8c && m.rx.in_service);
  assert(robotron_input(&m, 0x0c) == 0xe0);
  assert(m.rx.pending && m.cpu.bus.ack(&m) == 0xff);
  robotron_output(&m, 0x0e, 0x38);
  assert(m.cpu.bus.ack(&m) == 0x8c);
  robotron_output(&m, 0x0e, 0x38);
  assert(robotron_input(&m, 0x0c) == 0x61);
  assert(!(robotron_input(&m, 0x0e) & 1));
  for (unsigned i = 0; i < 4; i++)
    serial_byte(i, 1);
  assert(m.rx.count == 3 && (m.rx.errors & 0x20));
  for (unsigned i = 0; i < 3; i++)
    assert(robotron_input(&m, 0x0c) == i);
  robotron_output(&m, 0x0e, 0x30);
  assert(!m.rx.errors);
  serial_byte(0x55, 0);
  assert(m.rx.errors & 0x40);
  robotron_output(&m, 0x0e, 0x18);
  assert(!m.rx.count && !m.rx.errors);
  serial_byte(1, 1);
  assert(!m.rx.count); /* receiver disabled after reset */
  /* A tiny original ROM exercises the matrix/LED strobes through the CPU. */
  uint8_t rom[2048] = {0x01, 0x00, 0xc0,
                       0xed, 0x78, 0x76}; /* LD BC,C000; IN A,(C); HALT */
  robotron_keyboard k;
  robotron_keyboard_init(&k, rom, NULL, NULL);
  for (unsigned i = 0; i < 1000; i++)
    robotron_keyboard_tick(&k);
  assert(k.leds == 2); /* one toggle, despite a multi-cycle I/O read */
  assert(!robotron_keyboard_key(&k, 7, 5, 1) && k.matrix[7] == 32);
  assert(robotron_keyboard_key(&k, 13, 0, 1) < 0);
  assert(!robotron_keyboard_tap(&k, 61, 1));
  robotron_keyboard_tick(&k);
  assert(k.synthetic[7] == 32 && k.synthetic[8] == 2);
  robotron_keyboard_release(&k);
  assert(!k.matrix[7] && !k.synthetic[7] && !k.tap_count);
}
static void floppy_seek(void) {
  init();
  const uint8_t specify[] = {3, 0xf0, 0}, seek[] = {15, 0, 3};
  send(0x1d, specify, 3);
  send(0x1d, seek, 3);
  assert((robotron_input(&m, 0x1c) & 1) && m.fdc.cylinder[0] == 0);
  robotron_output(&m, 0x1d, 8);
  assert(robotron_input(&m, 0x1d) == 0x80);
  robotron_run(&m, 3994);
  assert(m.fdc.cylinder[0] == 0);
  robotron_run(&m, 1);
  assert(m.fdc.cylinder[0] == 1 && m.fdc.steps[0] == 1 && m.fdc.seeking);
  robotron_run(&m, 3994);
  assert(m.fdc.cylinder[0] == 2 && m.fdc.steps[0] == 2 && m.fdc.seeking);
  robotron_run(&m, 3994);
  assert(m.fdc.steps[0] == 3);
  robotron_output(&m, 0x1d, 8);
  assert(robotron_input(&m, 0x1d) == 0x20 && robotron_input(&m, 0x1d) == 3);
  assert(!(robotron_input(&m, 0x1c) & 1));
  const uint8_t absent[] = {4, 1};
  send(0x1d, absent, 2);
  assert(!(robotron_input(&m, 0x1d) & 32));
  fdc(0x46); /* read cylinder 0 without seeking back */
  robotron_run(&m, 3 * ROBOTRON_REVOLUTION_TICKS);
  assert(robotron_input(&m, 0x1d) & 0x40);
  assert(robotron_input(&m, 0x1d) == 4);
}

static void floppy_rotation(void) {
  init();
  robotron_run(&m, ROBOTRON_REVOLUTION_TICKS + 123);
  assert(m.rotation[0] == 123 && m.rotation[1] == 123);
  fdc(0x46);
  uint64_t expected = m.fdc.ready_at;
  assert(expected >
         m.cpu.cycles); /* Physical ID/data positions, not global CPU modulo. */
  m.motor = 128;
  robotron_run(&m, 1);
  assert(m.fdc.phase == 1 && (m.fdc.result[0] & 0x48) == 0x48);
  assert(m.drive[0].speed < ROBOTRON_SPINUP_TICKS); /* coast-down */
  init();
  m.fdc.cylinder[0] = m.fdc.physical[0] = 3;
  const uint8_t specify[] = {3, 0xf0, 0}, recal[] = {7, 0};
  send(0x1d, specify, 3);
  send(0x1d, recal, 2);
  robotron_run(&m, 3995);
  assert(m.fdc.physical[0] == 2);
  robotron_run(&m, 3994);
  assert(m.fdc.physical[0] == 1);
  robotron_run(&m, 3994);
  assert(m.fdc.physical[0] == 0 && !m.fdc.seeking);
}

static void two_drives_format(void) {
  static uint8_t b[819200];
  init();
  memset(b, 0xe5, sizeof(b));
  assert(!robotron_disk_unit(&m, 1, dac_memory_storage(b, sizeof(b), 1), 1));
  const uint8_t sense[] = {4, 1};
  send(0x1d, sense, 2);
  assert(robotron_input(&m, 0x1d) & 32);
  const uint8_t fmt[] = {0x4d, 1, 3, 5, 0x1b, 0xa6};
  send(0x1d, fmt, 6);
  for (unsigned i = 0; i < 20; i++) {
    while (m.fdc.search)
      robotron_run(&m, 1);
    if (m.fdc.ready_at > m.cpu.cycles)
      robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
    const uint8_t id[] = {0, 0, (uint8_t)(i / 4 + 1), 3};
    robotron_output(&m, 0x1d, id[i % 4]);
  }
  assert(m.fdc.search == 6);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles) + 1);
  assert(m.fdc.phase == 1 && m.disk_writes == 5);
  for (unsigned i = 0; i < 5120; i++)
    assert(b[i] == 0xa6);
  assert(b[5120] == 0xe5 && disk[0] == 0x5a);
  for (unsigned i = 0; i < 7; i++)
    robotron_input(&m, 0x1d);
  // Multi-track read crosses side 0 EOT to side 1 without seeking.
  memset(b + 5120, 0x39, 1024);
  const uint8_t read[] = {0xc6, 1, 0, 0, 5, 3, 5, 0x1b, 1};
  send(0x1d, read, 9);
  for (unsigned i = 0; i < 2048; i++) {
    if (m.fdc.search)
      robotron_run(&m, 1);
    m.cpu.cycles = m.fdc.ready_at;
    if (i == 2047)
      m.fdc.tc = 1;
    assert(robotron_input(&m, 0x1d) == (i < 1024 ? 0xa6 : 0x39));
  }
  assert(m.fdc.phase == 1 && m.fdc.cylinder[1] == 0 && m.fdc.result[4] == 1);
  robotron_output(&m, 0x20, 0);
  robotron_output(&m, 0x20, 0x40);
  for (unsigned u = 0; u < 4; u++) {
    robotron_output(&m, 0x1d, 8);
    assert(robotron_input(&m, 0x1d) == (0xc0 | u));
    robotron_input(&m, 0x1d);
  }
  robotron_output(&m, 0x1d, 8);
  assert(robotron_input(&m, 0x1d) == 0x80);
  assert(!robotron_disk_unit(&m, 1, dac_memory_storage(b, sizeof(b), 0), 0));
  send(0x1d, fmt, 6);
  robotron_input(&m, 0x1d);
  assert(robotron_input(&m, 0x1d) == 2);
}
static void printer(void) {
  init();
  uint8_t rom[2048] = {0x76};
  assert(!robotron_keyboard_load(&m, rom, sizeof(rom)));
  robotron_output(&m, 0x0e, 4);
  robotron_output(&m, 0x0e, 4); // x1, 1 stop
  robotron_output(&m, 0x0e, 5);
  robotron_output(&m, 0x0e, 0x68); // 8-bit TX
  robotron_output(&m, 0x0c, 'A');
  assert(!(robotron_input(&m, 0x0e) & 4));
  for (unsigned i = 0; i < 9; i++)
    robotron_printer_clock(&m);
  assert(!m.printer_size);
  robotron_printer_clock(&m);
  assert(m.printer_size == 1 && m.printer[0] == 'A');
  // CTC0 channel 0, 16 CPU clocks per serial clock.
  robotron_output(&m, 8, 7);
  robotron_output(&m, 8, 1);
  robotron_output(&m, 0x0c, 'B');
  robotron_run(&m, 160);
  assert(m.printer_size == 2 && m.printer[1] == 'B');
}
static void transmitter_interrupt(void) {
  init();
  m.sio_regs[0][1] = 2;
  m.sio_regs[0][4] = 4;
  m.sio_regs[0][5] = 0x68;
  m.sio_regs[1][1] = 4;
  m.sio_regs[1][2] = 0x80;
  assert(m.cpu.bus.ack(&m) == 0xff);
  robotron_output(&m, 0x0c, 'A');
  robotron_printer_clock(&m);
  assert(m.tx_pending && !m.tx_full);
  assert(m.cpu.bus.ack(&m) == 0x88 && m.tx_in_service);
  assert(m.cpu.bus.ack(&m) == 0xff);
  m.rx.pending = 1;
  assert(m.cpu.bus.ack(&m) == 0x8c); /* RX can interrupt TX */
  robotron_sio_control(&m, 0, 0x38);
  assert(!m.rx.in_service && m.tx_in_service);
  robotron_output(&m, 0x0c, 'B');
  assert(!m.tx_pending);
  robotron_sio_control(&m, 0, 0x38);
  assert(!m.tx_in_service);
  for (unsigned i = 0; i < 10; i++)
    robotron_printer_clock(&m);
  assert(m.tx_pending);
  robotron_sio_control(&m, 0, 0x28);
  assert(!m.tx_pending && m.cpu.bus.ack(&m) == 0xff);
}
static void floppy_mechanics_and_deadlines(void) {
  init();
  robotron_run(&m, ROBOTRON_REVOLUTION_TICKS + 1);
  assert(m.drive[0].index_count == 1 && !m.drive[1].index_count);
  assert(m.rotation[0] ==
         m.rotation[1]); /* empty motor turns without optical index */
  robotron_init(&m);
  m.rom[0] = 0x76;
  assert(!robotron_disk(&m, dac_memory_storage(disk, sizeof(disk), 1), 1));
  fdc(0x46);
  assert(m.fdc.phase == 1 &&
         (m.fdc.result[0] & 0x48) == 0x48); /* NR during startup */
  robotron_run(&m, ROBOTRON_SPINUP_TICKS - 1);
  assert(m.drive[0].speed == ROBOTRON_SPINUP_TICKS &&
         !robotron_drive_ready(&m, 0));
  robotron_run(&m, ROBOTRON_REVOLUTION_TICKS + 2);
  assert(robotron_drive_ready(&m, 0) && m.drive[0].index_count >= 2);
  unsigned phase = m.rotation[0];
  m.motor = 128;
  robotron_run(&m, 100);
  assert(!robotron_drive_ready(&m, 0) && m.rotation[0] != phase);
  robotron_run(&m, ROBOTRON_SPINUP_TICKS);
  phase = m.rotation[0];
  robotron_run(&m, 1000);
  assert(!m.drive[0].speed && m.rotation[0] == phase);

  init();
  m.rotation[0] = m.tracks[0][0].sector[2].id_phase - 20;
  const uint8_t rid[] = {0x4a, 0};
  send(0x1d, rid, 2);
  robotron_run(&m, 1);
  assert(m.fdc.phase == 2 && m.fdc.read_id &&
         !(robotron_input(&m, 0x1c) & 128));
  robotron_run(&m, 20);
  assert(m.fdc.phase == 1 && m.fdc.result[5] == 3 && m.fdc.result[1] == 0);
  init();
  m.drive[0].loaded = 0;
  fdc(0x46);
  assert(m.fdc.search == 1 && m.drive[0].load_at == ROBOTRON_HEAD_LOAD_TICKS);
  robotron_run(&m, ROBOTRON_HEAD_LOAD_TICKS - 2);
  assert(m.fdc.search == 1);
  robotron_run(&m, 2);
  assert(!m.fdc.search);

  init();
  fdc(0x46);
  uint64_t origin = m.fdc.byte_origin;
  for (unsigned i = 0; i < 1024; i++) {
    uint64_t due = origin + ((uint64_t)i * 79872 + 624) / 625;
    assert(m.fdc.ready_at == due);
    robotron_run(&m, (unsigned)(due - m.cpu.cycles));
    if (!i)
      assert(m.rotation[0] == m.tracks[0][0].sector[0].data_phase);
    assert(robotron_input(&m, 0x1c) & 128);
    if (i == 1023)
      m.fdc.tc = 1;
    assert(robotron_input(&m, 0x1d) == 0x5a);
  }
  assert(m.fdc.phase == 1 && m.fdc.result[1] == 0);
  init();
  fdc(0x45);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles) + 105);
  assert(m.fdc.phase == 2 && m.fdc.search == 5);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles) + 1);
  assert(m.fdc.phase == 1 && m.fdc.result[1] == 0x10 && m.disk_writes == 1);
  assert(disk[0] == 0 && disk[1023] == 0); /* underrun clocks zero padding */

  init();
  const uint8_t absent[] = {0x46, 0, 0, 0, 9, 3, 9, 27, 1};
  send(0x1d, absent, 9);
  robotron_run(&m, ROBOTRON_REVOLUTION_TICKS);
  assert(m.fdc.phase == 2 && m.fdc.search == 2);
  robotron_run(&m, ROBOTRON_REVOLUTION_TICKS + 2);
  assert(m.fdc.phase == 1 && m.fdc.result[1] == 4);

  init();
  m.fdc.cylinder[0] = m.fdc.physical[0] = 79;
  const uint8_t spec[] = {3, 0xf1, 2}, recal[] = {7, 0};
  send(0x1d, spec, 3);
  send(0x1d, recal, 2);
  robotron_run(&m, 77 * 3994 + 1);
  assert(m.fdc.physical[0] == 2 && m.fdc.seek_status[0] == 0x70 &&
         !m.fdc.seeking);
  send(0x1d, recal, 2);
  robotron_run(&m, 2 * 3994 + 1);
  assert(!m.fdc.physical[0] && m.fdc.seek_status[0] == 0x20);
  init();
  const uint8_t seek[] = {15, 0, 1};
  send(0x1d, seek, 3);
  robotron_run(&m, 23963);
  assert(m.fdc.physical[0] == 1 && robotron_head_position(&m, 0) < 65536);
  robotron_run(&m, ROBOTRON_STEP_TICKS / 2);
  unsigned halfway = robotron_head_position(&m, 0);
  assert(halfway > 32000 && halfway < 33500);
  robotron_run(&m, ROBOTRON_STEP_TICKS);
  assert(robotron_head_position(&m, 0) == 65536);
}
static void floppy_dsk(void) {
  const unsigned length = 256 + 160 * 5376;
  uint8_t *dsk = calloc(1, length);
  assert(dsk);
  memcpy(dsk, "MV - CPCEMU Disk-File\r\nDisk-Info\r\n", 34);
  dsk[0x30] = 80;
  dsk[0x31] = 2;
  dsk[0x33] = 21;
  const uint8_t order[] = {3, 1, 5, 2, 4};
  for (unsigned t = 0; t < 160; t++) {
    uint8_t *h = dsk + 256 + t * 5376;
    memcpy(h, "Track-Info\r\n", 12);
    h[0x10] = t / 2;
    h[0x11] = t % 2;
    h[0x14] = 3;
    h[0x15] = 5;
    h[0x16] = 27;
    for (unsigned i = 0; i < 5; i++) {
      uint8_t *id = h + 0x18 + 8 * i;
      id[0] = t / 2;
      id[1] = t % 2;
      id[2] = order[i];
      id[3] = 3;
      id[7] = 4;
      memset(h + 256 + 1024 * i, order[i], 1024);
    }
  }
  init();
  assert(!robotron_disk(&m, dac_memory_storage(dsk, length, 1), 1));
  assert(m.disk_format[0] == 1 && m.tracks[0][0].sector[0].r == 3);
  fdc(0x46); /* R=1 resides in physical slot one, not slot zero. */
  assert(m.fdc.slot == 1);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
  assert(robotron_input(&m, 0x1d) == 1);
  robotron_run(&m, 300); /* intentionally overrun and drain result */
  for (unsigned i = 0; i < 7; i++)
    robotron_input(&m, 0x1d);
  const uint8_t ids[] = {0, 0, 5, 3, 0, 0, 4, 3, 0, 0,
                         3, 3, 0, 0, 2, 3, 0, 0, 1, 3};
  assert(!robotron_format_track(&m, 0, 0, 0, ids, 54, 0xa6));
  assert(dsk[256 + 0x1a] == 5 && dsk[256 + 0x16] == 54 && dsk[512] == 0xa6);
  assert(!robotron_disk(&m, dac_memory_storage(dsk, length, 1), 1));
  assert(m.tracks[0][0].sector[0].r == 5 && m.tracks[0][0].gap == 54);
  assert(robotron_disk(&m, dac_memory_storage(dsk, length - 1, 1), 1) < 0);
  assert(m.tracks[0][0].sector[0].r == 5); /* rejected mount is atomic */
  memcpy(dsk, "EXTENDED CPC DSK File\r\nDisk-Info\r\n", 34);
  memset(dsk + 0x34, 21, 160);
  assert(!robotron_disk(&m, dac_memory_storage(dsk, length, 1), 1));
  assert(m.disk_format[0] == 2);
  /* ID CRC fails before data transfer; a data CRC does not invalidate Read-ID.
   */
  dsk[256 + 0x1c] = 0x20;
  dsk[256 + 0x1d] = 0;
  init();
  assert(!robotron_disk(&m, dac_memory_storage(dsk, length, 1), 1));
  m.rotation[0] = m.tracks[0][0].sector[0].id_phase - 20;
  const uint8_t rid[] = {0x4a, 0};
  send(0x1d, rid, 2);
  robotron_run(&m, 21);
  assert(m.fdc.phase == 1 && m.fdc.result[1] == 0x20 && !m.disk_reads);
  dsk[256 + 0x1d] = 0x20;
  init();
  assert(!robotron_disk(&m, dac_memory_storage(dsk, length, 1), 1));
  m.rotation[0] = m.tracks[0][0].sector[0].id_phase - 20;
  send(0x1d, rid, 2);
  robotron_run(&m, 21);
  assert(m.fdc.phase == 1 && !m.fdc.result[1]);
  /* Physical side 0 may carry a logical H=7, C=12 in a DSK header. */
  dsk[256 + 0x18] = 12;
  dsk[256 + 0x19] = 7;
  dsk[256 + 0x1c] = dsk[256 + 0x1d] = 0;
  init();
  assert(!robotron_disk(&m, dac_memory_storage(dsk, length, 1), 1));
  const uint8_t logical[] = {0x46, 0, 12, 7, 5, 3, 5, 27, 1};
  send(0x1d, logical, 9);
  robotron_run(&m, 1);
  assert(!m.fdc.search && m.fdc.slot == 0);
  robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
  assert(robotron_input(&m, 0x1d) == 0xa6);
  dsk[256 + 0x1f] =
      8; /* oversized/weak sector payload is rejected, never flattened */
  assert(robotron_disk_validate(dac_memory_storage(dsk, length, 0)) < 0);
  free(dsk);
}

static void drain_result(void) {
  assert(m.fdc.phase == 1);
  while (m.fdc.phase == 1)
    robotron_input(&m, 0x1d);
}
static void wait_data(void) {
  unsigned budget = 3 * ROBOTRON_REVOLUTION_TICKS;
  while (m.fdc.phase == 2 && m.fdc.search && budget--)
    robotron_run(&m, 1);
  if (!(budget && m.fdc.phase == 2 && !m.fdc.search))
    fprintf(
        stderr,
        "wait op=%x R=%u N=%u phase=%u search=%u result=%x/%x/%x count=%u\n",
        m.fdc.command[0], m.fdc.sector, m.fdc.n, m.fdc.phase, m.fdc.search,
        m.fdc.result[0], m.fdc.result[1], m.fdc.result[2], m.fdc.track_count);
  assert(budget && m.fdc.phase == 2 && !m.fdc.search);
  if (m.fdc.ready_at > m.cpu.cycles)
    robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
}
static void data_command(unsigned op, unsigned r, unsigned n, unsigned eot) {
  uint8_t c[] = {op, 0, 0, 0, r, n, eot, 27, 128};
  send(0x1d, c, 9);
}
/* Small owner-independent EDSK fixture: one cylinder/side, arbitrary CHRN
 * order. The rest of the 80-track drive is physically blank. */
static uint8_t *layout(const unsigned *sizes, unsigned count,
                       unsigned *length) {
  unsigned payload = 0;
  for (unsigned i = 0; i < count; i++)
    payload += 128u << sizes[i];
  unsigned track_size = (256 + payload + 255) & ~255u;
  *length = 256 + track_size;
  uint8_t *b = calloc(1, *length);
  assert(b);
  memcpy(b, "EXTENDED CPC DSK File\r\nDisk-Info\r\n", 34);
  b[0x30] = b[0x31] = 1;
  b[0x34] = track_size / 256;
  memcpy(b + 256, "Track-Info\r\n", 12);
  b[256 + 0x14] = sizes[0];
  b[256 + 0x15] = count;
  b[256 + 0x16] = 27;
  unsigned offset = 512;
  for (unsigned i = 0; i < count; i++) {
    uint8_t *id = b + 256 + 0x18 + i * 8;
    unsigned bytes = 128u << sizes[i];
    id[2] = (uint8_t)(7 - i * 2);
    id[3] = sizes[i];
    id[6] = bytes;
    id[7] = bytes >> 8;
    memset(b + offset, 0x31 + i, bytes);
    offset += bytes;
  }
  return b;
}
static void floppy_layout_commands(void) {
  const unsigned mixed[] = {0, 1, 2, 3, 4, 5};
  /* Each supported size, including N=0/DTL, remains bounded by track capacity.
   */
  for (unsigned n = 0; n < 6; n++) {
    unsigned length;
    uint8_t *b = layout(mixed + n, 1, &length);
    init();
    assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
    assert(m.tracks[0][0].count == 1 && !m.tracks[0][1].count);
    data_command(0x46, 7, n, 7);
    wait_data();
    unsigned bytes = 128u << n;
    uint64_t origin = m.fdc.byte_origin;
    for (unsigned i = 0; i < bytes; i++) {
      if (m.fdc.ready_at > m.cpu.cycles)
        robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
      assert(m.cpu.cycles == origin + ((uint64_t)i * 79872 + 624) / 625);
      if (i == bytes - 1)
        m.fdc.tc = 1;
      assert(robotron_input(&m, 0x1d) == 0x31);
    }
    assert(m.fdc.phase == 1 && !m.fdc.result[1]);
    free(b);
  }
  unsigned length;
  uint8_t *b = layout(mixed, 3, &length);
  init();
  assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
  assert(m.tracks[0][0].sector[2].offset == 512 + 128 + 256);
  data_command(0x46, 3, 2, 3);
  wait_data();
  assert(robotron_input(&m, 0x1d) == 0x33);
  free(b);

  unsigned small[29] = {0};
  b = layout(small, 29, &length);
  assert(robotron_disk_validate(dac_memory_storage(b, length, 0)) <
         0); // too much GAP3
  b[256 + 0x16] = 0;
  init();
  assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
  assert(m.tracks[0][0].count == 29 &&
         m.tracks[0][0].sector[28].offset == 512 + 28 * 128);
  b[256 + 0x15] = 30; // would overrun the fixed DSK sector table
  assert(robotron_disk_validate(dac_memory_storage(b, length, 0)) < 0);
  free(b);
  const unsigned same[] = {1, 1, 1};
  b = layout(same, 3, &length);
  init();
  assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
  data_command(0x49, 7, 1, 7);
  wait_data();
  for (unsigned i = 0; i < 256; i++) {
    if (m.fdc.ready_at > m.cpu.cycles)
      robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
    if (i == 255)
      m.fdc.tc = 1;
    robotron_output(&m, 0x1d, 0xa7);
  }
  assert(m.fdc.phase == 1 && !m.fdc.result[1] && !m.fdc.result[2]);
  assert(b[256 + 0x1d] == 0x40 && b[512] == 0xa7);
  drain_result();
  data_command(0x4c, 7, 1, 7);
  wait_data();
  for (unsigned i = 0; i < 256; i++) {
    if (m.fdc.ready_at > m.cpu.cycles)
      robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
    if (i == 255)
      m.fdc.tc = 1;
    assert(robotron_input(&m, 0x1d) == 0xa7);
  }
  assert(!m.fdc.result[1] && !m.fdc.result[2]);
  drain_result();
  data_command(0x46, 7, 1, 7);
  wait_data();
  m.fdc.tc = 1;
  for (unsigned i = 0; i < 256; i++) {
    if (m.fdc.ready_at > m.cpu.cycles)
      robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
    robotron_input(&m, 0x1d);
  }
  assert(m.fdc.result[2] == 0x40);
  drain_result();
  /* Read Track waits for index, reads physical order 7/5/3 and ignores deleted
   * marks. A CRC error is accumulated without cutting off later sectors. */
  b[256 + 0x1c + 8] = b[256 + 0x1d + 8] = 0x20;
  assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
  data_command(0x42, 3, 1, 3);
  robotron_run(&m, 1);
  assert(m.fdc.search == 4);
  unsigned index = m.drive[0].index_count;
  for (unsigned sector = 0; sector < 3; sector++) {
    wait_data();
    assert(m.drive[0].index_count > index);
    assert(m.fdc.slot == sector);
    for (unsigned i = 0; i < 256; i++) {
      if (m.fdc.ready_at > m.cpu.cycles)
        robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
      if (sector == 2 && i == 255)
        m.fdc.tc = 1;
      assert(robotron_input(&m, 0x1d) == (sector ? 0x31 + sector : 0xa7));
    }
  }
  assert(m.fdc.phase == 1 && m.fdc.result[1] == 0x20 &&
         m.fdc.result[2] == 0x20);
  drain_result();
  /* A motor interruption persists the written prefix and marks bad CRC in DSK.
   */
  data_command(0x45, 7, 1, 7);
  wait_data();
  robotron_output(&m, 0x1d, 0x19);
  m.motor |= 128;
  robotron_run(&m, 1);
  assert(m.fdc.phase == 1 && (m.fdc.result[0] & 0x48) == 0x48);
  assert(b[512] == 0x19 && b[513] == 0xa7 && b[256 + 0x1c] == 0x20 &&
         b[256 + 0x1d] == 0x20);
  assert(!robotron_disk_validate(dac_memory_storage(b, length, 0)));
  free(b);
  /* Formatting clocks each payload before accepting the next tuple. A later
   * underrun keeps sectors already completed, without modifying the rest. */
  b = layout(same, 3, &length);
  init();
  assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
  const uint8_t fmt[] = {0x4d, 0, 1, 3, 27, 0xe9};
  send(0x1d, fmt, 6);
  wait_data();
  const uint8_t id[] = {0, 0, 2, 1};
  uint64_t start = m.cpu.cycles;
  for (unsigned i = 0; i < 4; i++) {
    if (m.fdc.ready_at > m.cpu.cycles)
      robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
    robotron_output(&m, 0x1d, id[i]);
  }
  assert(m.fdc.search == 6 && b[512] == 0x31 && m.fdc.ready_at - start > 30000);
  wait_data(); // first payload was clocked out; second tuple is now requested
  assert(b[512] == 0xe9 && b[768] == 0x32 && b[256 + 0x1a] == 2);
  robotron_run(&m, 105);
  assert(m.fdc.phase == 1 && m.fdc.result[1] == 0x10 && m.disk_writes == 1);
  assert(!robotron_disk_validate(dac_memory_storage(b, length, 0)));
  free(b);
}

int main(void) {
  floppy_mechanics_and_deadlines();
  floppy_dsk();
  floppy_layout_commands();
  transmitter_interrupt();
  two_drives_format();
  printer();
  keyboard_serial();
  floppy_seek();
  floppy_rotation();
  dma_memory();
  floppy_completion();
  interrupt_chain();
  timer_cascade();
  display();
  puts("PASS Robotron DMA/RDY/TC, FDC reset/status, daisy-chain/RETI, "
       "CRTC/attributes/cursor");
}
