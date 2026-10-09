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
  robotron_run(&m, 5024);
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
  robotron_run(&m, 4128);
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
  robotron_run(&m, 4128);
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
  robotron_output(&m, 0x19, 0x40);
  robotron_video(&m, pixels, &w, &h);
  assert(robotron_input(&m, 0x19) == 0x40);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
}
int main(void) {
  dma_memory();
  floppy_completion();
  interrupt_chain();
  timer_cascade();
  display();
  puts("PASS Robotron DMA/RDY/TC, FDC reset/status, daisy-chain/RETI, "
       "CRTC/attributes/cursor");
}
