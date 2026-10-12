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
  robotron_run(&m, 4000 + 1024 * 128);
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
  robotron_run(&m, 4000 + 128 * 128);
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
  robotron_run(&m, 4000 + 128 * 128);
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
  assert(robotron_input(&m, 0x1d) & 0x40);
  assert(robotron_input(&m, 0x1d) == 4);
}

static void floppy_rotation(void) {
  init();
  m.motor = 8; /* A on, B off. */
  robotron_run(&m, ROBOTRON_REVOLUTION_TICKS + 123);
  assert(m.rotation[0] == 123 && m.rotation[1] == 0);
  m.motor = 128; /* Independent phase; B starts where it stopped. */
  robotron_run(&m, 456);
  assert(m.rotation[0] == 123 && m.rotation[1] == 456);
  m.motor = 0;
  fdc(0x46);
  uint64_t expected = m.cpu.cycles + ROBOTRON_REVOLUTION_TICKS - 123 + 4000;
  assert(m.fdc.ready_at == expected); /* Uses A phase, not global CPU time. */
  m.motor = 128;
  robotron_run(&m, 500);
  assert(m.rotation[0] == 123 && m.fdc.ready_at == expected + 500);
  m.fdc.ready_at = m.cpu.cycles; /* Already-ready byte still cannot transfer with motor off. */
  assert(robotron_input(&m, 0x1d) == 0xff && m.fdc.data_pos == 0);
  m.fdc.ready_at = expected + 500;
  m.motor = 0;
  robotron_run(&m, 100);
  assert(m.rotation[0] == 223 && m.fdc.ready_at == expected + 500);
  /* Backward seeks also expose every step, not just the destination. */
  init(); m.fdc.cylinder[0] = 3;
  const uint8_t specify[] = {3, 0xf0, 0}, recal[] = {7, 0};
  send(0x1d, specify, 3); send(0x1d, recal, 2);
  robotron_run(&m, 3995); assert(m.fdc.cylinder[0] == 2);
  robotron_run(&m, 3994); assert(m.fdc.cylinder[0] == 1);
  robotron_run(&m, 3994); assert(m.fdc.cylinder[0] == 0 && !m.fdc.seeking);
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
    m.cpu.cycles = m.fdc.ready_at;
    const uint8_t id[] = {0, 0, (uint8_t)(i / 4 + 1), 3};
    robotron_output(&m, 0x1d, id[i % 4]);
  }
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
int main(void) {
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
