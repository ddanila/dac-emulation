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
                       0x14, bmode, 0xbd, b,      b >> 8, ctrl,
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
  robotron_run(&m, 8 * 6);
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
  robotron_run(&m, 8 * 6);
  assert(!m.dma.irq && !m.dma.remaining);
}
static void dma_phases(void) {
  for (unsigned timing = 0; timing < 3; timing++) {
    init();
    m.ram[0x4000] = 0x31;
    m.ram[0x5000] = 0;
    dma(0x4000, 0x5000, 1, 0x10, 0x10);
    robotron_output(&m, 0, 0x54);
    robotron_output(&m, 0, timing);
    robotron_output(&m, 0, 0x50);
    robotron_output(&m, 0, 2);
    robotron_output(&m, 0, 0xb3);
    robotron_output(&m, 0, 0x87);
    uint64_t cycles = m.cpu.cycles;
    unsigned pc = m.cpu.cpu.pc;
    robotron_run(&m, 4 - timing);
    assert(m.dma.phase == 2 && m.dma.latch == 0x31 && !m.ram[0x5000]);
    m.ram[0x4000] = 0x72;
    m.dma.force_ready = 0; /* RDY falls after the read. */
    robotron_run(&m, 1);
    assert(!m.ram[0x5000]);
    robotron_run(&m, 1);
    assert(m.ram[0x5000] == 0x31 && !m.dma.remaining);
    assert(m.cpu.cycles == cycles + 6 - timing && m.cpu.cpu.pc == pc);
  }
}
static void dma_search_wait_reset(void) {
  for (unsigned operation = 2; operation <= 3; operation++) {
    init();
    m.ram[0x4000] = 0x11;
    m.ram[0x4001] = 0xa5;
    dma(0x4000, 0x5000, 4, 0x10, 0x31);
    robotron_output(&m, 0, 4 | operation);
    const uint8_t match[] = {0xbc, 0x0f, 0xa0, 0xb3, 0x87};
    send(0, match, sizeof(match));
    robotron_run(&m, 30);
    assert(!m.dma.enabled && m.dma.remaining == 2 && m.dma.transferred == 2);
    assert(!(m.dma.status & 0x10) && m.dma.irq);
    assert(m.cpu.bus.ack(&m) == 0x22);
    assert(m.ram[0x5000] == (operation == 3 ? 0x11 : 0));
    assert(m.ram[0x5001] == (operation == 3 ? 0xa5 : 0));
    assert(m.dma.run_b == (operation == 3 ? 0x5002 : 0x5000));
  }
  init();
  m.ram[0x4000] = 0x71;
  dma(0x4000, 0x5000, 1, 0x10, 0x10);
  m.dma.wait = 1;
  robotron_output(&m, 0, 0xb3);
  robotron_output(&m, 0, 0x87);
  robotron_run(&m, 100);
  assert(m.dma.phase == 1 && m.dma.ticks == 1 && !m.ram[0x5000]);
  m.dma.wait = 0;
  robotron_run(&m, 4);
  assert(m.ram[0x5000] == 0x71);
  const uint8_t timing[] = {0x54, 2, 0x50, 1};
  send(0, timing, sizeof(timing));
  robotron_output(&m, 0, 0xc7);
  assert(!m.dma.a_timing && m.dma.b_timing);
  robotron_output(&m, 0, 0xcb);
  assert(!m.dma.b_timing);
  const uint8_t readmask[] = {0xbb, 0x7e};
  send(0, readmask, 2);
  robotron_input(&m, 0);
  unsigned pos = m.dma.read_pos;
  robotron_output(&m, 0, 0xc3);
  assert(m.dma.read_pos == pos && m.dma.mask == 0x7e && m.dma.a == 0x4000);
  /* Reset sequence escapes a partially written WR4 parameter group. */
  robotron_output(&m, 0, 0x9d);
  for (unsigned i = 0; i < 6; i++)
    robotron_output(&m, 0, 0xc3);
  assert(!m.dma.tag_count && !m.dma.enabled && !m.dma.irq);
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
static void scan_display(void) {
  robotron_output(&m, 0x19, 0x20 | m.raster.dma);
  robotron_run(&m, 80000);
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
  if (m.display_on)
    scan_display();
  robotron_video(&m, pixels, &w, &h);
  assert(w == 32 && h == 3);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
  robotron_output(&m, 0x19, 0x20);
  assert(robotron_input(&m, 0x19) == 0x44);
  if (m.display_on)
    scan_display();
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[1] == 0xff101812);
  assert(pixels[8] == 0xff101812); /* visible attribute is blank */
  assert(pixels[16] == 0xff83e7a0 && pixels[17] == 0xff101812);
  robotron_output(&m, 0x19, 0x80);
  const uint8_t cursor[] = {0, 0};
  send(0x18, cursor, 2);
  if (m.display_on)
    scan_display();
  robotron_video(&m, pixels, &w, &h);
  for (unsigned x = 0; x < 8; x++)
    assert(pixels[w + x] == 0xff83e7a0);
  assert(m.crtc[0] == 3 &&
         m.crtc[2] == 0x12); /* cursor cannot overwrite geometry */
  // Character-attribute code suppresses the upper glyph region via VSP,
  // with no preceding field attributes in this row.
  m.cursor[0] = 255;
  m.vram[0] = 0xc0;
  for (unsigned y = 0; y < 3; y++)
    m.chargen[y * 128 + 0x40] = 0x80;
  if (m.display_on)
    scan_display();
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff101812 && pixels[w] == 0xff83e7a0 &&
         pixels[2 * w] == 0xff83e7a0);
  /* Invisible FA's next byte is seven-bit glyph data, not end-screen. */
  m.crtc[3] &= ~64;
  m.vram[0] = 0x80;
  m.vram[1] = 0xf2;
  m.vram[2] = 'A';
  m.chargen[0x72] = 0x80;
  if (m.display_on)
    scan_display();
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[8] == 0xff83e7a0);
  /* A CA inherits reverse/GPA but not field highlight. */
  m.crtc[3] |= 64;
  m.vram[0] = 0x95;
  m.vram[1] = 0xc0;
  m.chargen[2048 + 128 + 0x40] = 0x80;
  if (m.display_on)
    scan_display();
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[8] == 0xff83e7a0); /* VSP then field reverse */
  assert(pixels[w + 8] == 0xff101812 && pixels[w + 9] == 0xff83e7a0);
  /* Error flags clear on read; IE/VE survive repeated reads. */
  m.crtc_status = 0x7f;
  assert(robotron_input(&m, 0x19) == 0x7f);
  assert(robotron_input(&m, 0x19) == 0x44);
  robotron_output(&m, 0x18, 0); /* too many parameters */
  assert(robotron_input(&m, 0x19) == 0x4c);
  robotron_output(&m, 0x19, 0x80); /* cursor needs two bytes */
  robotron_output(&m, 0x18, 0);
  robotron_output(&m, 0x19, 0x20); /* interrupted after one */
  assert(robotron_input(&m, 0x19) == 0x4c);
  assert(robotron_input(&m, 0x19) == 0x44);
  robotron_output(&m, 0x19, 0x40);
  if (m.display_on)
    scan_display();
  robotron_video(&m, pixels, &w, &h);
  assert(robotron_input(&m, 0x19) == 0x40);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
}
static void display_fifo(void) {
  unsigned w, h;
  for (unsigned count = 16; count <= 33; count++) {
    init();
    m.crtc[0] = count - 1;
    m.crtc[1] = 1;
    m.crtc[2] = 3;
    m.crtc[3] = 0x30;
    m.cursor[0] = 255;
    for (unsigned i = 0; i < count; i++) {
      m.vram[2 * i] = 0x80;
      m.vram[2 * i + 1] = 0x80 | (i + 1); /* top bit discarded */
      m.chargen[i + 1] = i + 1;
    }
    /* A second row starts with a fresh FIFO read/write index. */
    m.vram[2 * count] = 0x80;
    m.vram[2 * count + 1] = 0x41;
    m.chargen[0x41] = 0xa5;
    robotron_output(&m, 0x19, 0x20);
    robotron_output(&m, 0x19, 0xc0); /* isolate FO from raster IR */
    /* Rendering alone cannot set/clear FO or alter emulation state. */
    assert(robotron_input(&m, 0x19) == 4);
    // Row fill completes after 2*count character clocks, before frame end.
    unsigned fill_ticks = (2 * (count > 16 ? 17 : count) * 104 + 44) / 45;
    robotron_run(&m, fill_ticks - 1);
    assert(robotron_input(&m, 0x19) == 4);
    robotron_run(&m, 1);
    assert(robotron_input(&m, 0x19) == (count > 16 ? 5 : 4));
    assert(robotron_input(&m, 0x19) == 4);
    robotron_run(&m, 80000);
    assert(robotron_input(&m, 0x19) == (count > 16 ? 5 : 4));
    robotron_video(&m, pixels, &w, &h);
    assert(w == count * 8 && h == 8);
    for (unsigned col = 0; col < count; col++) {
      unsigned last = col % 16;
      while (last + 16 < count)
        last += 16;
      for (unsigned x = 0; x < 8; x++)
        assert(pixels[col * 8 + x] ==
               (((last + 1) & (128 >> x)) ? 0xff83e7a0 : 0xff101812));
    }
    for (unsigned x = 0; x < 8; x++)
      assert(pixels[4 * w + x] ==
             ((0xa5 & (128 >> x)) ? 0xff83e7a0 : 0xff101812));
    m.crtc[3] |= 64;
    robotron_output(&m, 0x19, 0x20);
    robotron_output(&m, 0x19, 0xc0);
    robotron_run(&m, 80000);
    assert(robotron_input(&m, 0x19) == 4);
    robotron_output(&m, 0x19, 0x40);
    robotron_run(&m, 80000);
    assert(robotron_input(&m, 0x19) == 0);
  }
}

static unsigned clocks_to_ticks(unsigned clocks) {
  return (clocks * 104 + 44) / 45;
}
static void display_schedule(void) {
  unsigned w, h;
  init();
  m.crtc[0] = 3;
  m.crtc[1] = 1;
  m.crtc[2] = 3;
  m.crtc[3] = 0x70;
  m.cursor[0] = 255;
  m.chargen['A'] = 0x80;
  m.chargen['B'] = 0x40;
  m.vram[0] = 'A';
  m.vram[1] = 0xf1;
  m.vram[2] = 'B';
  robotron_output(&m, 0x19, 0x20); // Single-byte burst: no dummy byte.
  robotron_run(&m, clocks_to_ticks(2));
  assert(m.raster.stream == 2 && !m.raster.remaining);
  robotron_run(&m, clocks_to_ticks(48));
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[4 * w + 1] == 0xff83e7a0);
  // Four-byte burst requires dummy following mid-burst stop.
  m.vram[2] = 0xff;
  m.vram[3] = 'B';
  robotron_output(&m, 0x19, 0x22);
  robotron_run(&m, clocks_to_ticks(3));
  assert(m.raster.stream == 3 && !m.raster.remaining);
  robotron_run(&m, clocks_to_ticks(48));
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[4 * w + 1] == 0xff83e7a0);
  m.vram[0] = 0xf3;
  robotron_output(&m, 0x19, 0x22);
  robotron_run(&m, clocks_to_ticks(2));
  assert(m.raster.stream == 2 && m.raster.stopped == 1);
  robotron_run(&m, clocks_to_ticks(24));
  assert(m.raster.stream == 2); // No next-row DMA after stop-screen.

  init();
  m.crtc[0] = 3;
  m.crtc[1] = 1;
  m.crtc[2] = 3;
  m.crtc[3] = 0x70;
  robotron_output(&m, 0x19, 0x20);
  // 6 character clocks x 4 scanlines = 24 per row. Initial prefill then row0.
  unsigned last_row = clocks_to_ticks(48);
  robotron_run(&m, last_row - 1);
  assert(!(robotron_input(&m, 0x19) & 32));
  robotron_run(&m, 1);
  assert(robotron_input(&m, 0x19) & 32);
  assert(!(robotron_input(&m, 0x19) & 32));
  robotron_output(&m, 0x19, 0xc0);
  robotron_run(&m, clocks_to_ticks(72));
  assert(!(robotron_input(&m, 0x19) & 32));
  // Chunking and rendering never advance/modify the hardware scheduler.
  robotron_raster before = m.raster;
  robotron_video(&m, pixels, &w, &h);
  assert(!memcmp(&before, &m.raster, sizeof(before)));
  robotron_output(&m, 0x19, 0x20);
  m.raster.frames = 0;
  robotron_run(&m, 1000);
  before = m.raster;
  robotron_output(&m, 0x19, 0x20);
  m.raster.frames = 0;
  for (unsigned i = 0; i < 1000; i++)
    robotron_run(&m, 1);
  assert(!memcmp(&before, &m.raster, sizeof(before)));
  robotron_output(&m, 0x19, 0xe0);
  before = m.raster;
  robotron_run(&m, 1000);
  assert(!memcmp(&before, &m.raster, sizeof(before)));

  // An intentionally impossible burst schedule misses the first row deadline.
  init();
  m.crtc[0] = 79;
  m.crtc[1] = 1;
  m.crtc[2] = 0;
  m.crtc[3] = 0x70;
  m.vram[0] = 'A';
  m.chargen['A'] = 0xff;
  m.cursor[0] = 255;
  robotron_output(&m, 0x19, 0x3c); // 1 byte/burst, 55 clocks between bursts.
  robotron_run(&m, clocks_to_ticks(82));
  assert(robotron_input(&m, 0x19) & 2);
  assert(!(robotron_input(&m, 0x19) & 2));
  assert(m.raster.underrun && m.raster.blank_from == 0);
  robotron_video(&m, pixels, &w, &h);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
  robotron_run(&m, clocks_to_ticks(164)); // Final retrace releases suppression.
  assert(!m.raster.underrun && m.raster.blank_from == 0);
  robotron_output(&m, 0x19, 0x20); // Fast restart releases suppression.
  assert(m.raster.blank_from == 24);
  robotron_output(&m, 0x19, 0x40);
  assert(!m.raster.remaining);
}

static void display_latched_rows(void) {
  unsigned w, h;
  init();
  m.crtc[0] = 3;
  m.crtc[1] = 1;
  m.crtc[2] = 3;
  m.crtc[3] = 0x70;
  m.cursor[0] = 255;
  m.chargen['A'] = 0x80;
  m.chargen['B'] = 0x40;
  m.vram[0] = 'A';
  robotron_output(&m, 0x19, 0x20);
  robotron_run(&m, clocks_to_ticks(1));
  m.vram[0] = 'B'; // Write after first DACK: that byte retains A.
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff101812);
  robotron_run(&m, clocks_to_ticks(24));
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[1] == 0xff101812);
  robotron_raster saved = m.raster;
  robotron_video(&m, pixels, &w, &h);
  assert(!memcmp(&saved, &m.raster, sizeof(saved)));
  robotron_run(&m, clocks_to_ticks(72));
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff101812 && pixels[1] == 0xff83e7a0);
  // A newly latched first row cannot change the old second row's field state.
  m.vram[0] = 0x90;
  m.vram[4] = 'A';
  robotron_output(&m, 0x19, 0x20);
  robotron_run(&m, clocks_to_ticks(48));
  assert(m.raster.scanout[1].field == 16);
  m.vram[0] = 0x80;
  robotron_run(&m, clocks_to_ticks(48));
  assert(m.raster.scanout[1].field == 16);
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[4 * w] == 0xff101812 && pixels[4 * w + 1] == 0xff83e7a0);
  robotron_run(&m, clocks_to_ticks(24));
  robotron_video(&m, pixels, &w, &h);
  assert(m.raster.scanout[1].field == 0 && pixels[4 * w] == 0xff83e7a0);
}

static void display_byte_fetch(void) {
  unsigned w, h;
  init();
  m.crtc[0] = 3;
  m.crtc[1] = 1;
  m.crtc[2] = 3;
  m.crtc[3] = 0x70;
  m.cursor[0] = 255;
  m.chargen['A'] = 0x80;
  m.chargen['B'] = 0x40;
  memset(m.vram, 'A', 8);
  robotron_output(&m, 0x19, 0x20);
  assert(m.raster.stream == 0); // Start command itself never reads VRAM.
  robotron_run(&m, clocks_to_ticks(1));
  assert(m.raster.stream == 1);
  m.vram[0] = 'B';
  m.vram[1] = 'B';
  robotron_run(&m, clocks_to_ticks(23));
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[1] == 0xff101812);
  assert(pixels[8] == 0xff101812 && pixels[9] == 0xff83e7a0);
  // A later glyph/cursor/attribute change cannot repaint an already scanned
  // row.
  m.chargen['A'] = 0xff;
  m.cursor[0] = 0;
  m.cursor[1] = 0;
  m.crtc[3] = 0x40;
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[1] == 0xff101812);

  init();
  m.crtc[0] = 3;
  m.crtc[1] = 1;
  m.crtc[2] = 15;
  m.crtc[3] = 0x70;
  memset(m.vram, 'A', 8);
  robotron_output(&m, 0x19, 0x24); // one byte, seven-clock gap
  robotron_run(&m, clocks_to_ticks(1));
  assert(m.raster.stream == 1);
  robotron_run(&m, clocks_to_ticks(7));
  assert(m.raster.stream == 1);
  m.vram[1] = 'B';
  robotron_run(&m, clocks_to_ticks(1));
  assert(m.raster.stream == 2 && m.raster.pending_row.code[1] == 'B');

  // The byte following an invisible attribute is independently fetched.
  init();
  m.crtc[0] = 1;
  m.crtc[1] = 1;
  m.crtc[2] = 15;
  m.crtc[3] = 0x30;
  m.vram[0] = 0x80;
  m.vram[1] = 'A';
  robotron_output(&m, 0x19, 0x24);
  robotron_run(&m, clocks_to_ticks(1));
  assert(m.raster.fetch_phase == 1);
  m.vram[1] = 0xc2;
  robotron_run(&m, clocks_to_ticks(8));
  assert(m.raster.pending_row.fifo[0] == 0x42 && m.raster.fetch_fifo == 1);
}

/* A scanline must retain its emitted glyph/cursor state while future lines
 * sample changes. Test the boundary itself, plus deterministic mid-line resume.
 */
static void display_scanlines(void) {
  unsigned w, h;
  init();
  m.crtc[0] = 3;
  m.crtc[1] = 1;
  m.crtc[2] = 3;
  m.crtc[3] = 0x70;
  m.cursor[0] = 255;
  memset(m.vram, 'A', 8);
  for (unsigned y = 0; y < 4; y++)
    m.chargen[y * 128 + 'A'] = 0x80;
  robotron_output(&m, 0x19, 0x20);
  robotron_run(&m, clocks_to_ticks(24)); // row 0, line 0 emitted
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[w] == 0xff101812);
  m.chargen[128 + 'A'] = 0x40;
  while (m.raster.character < 5)
    robotron_run(&m, 1);
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[w + 1] == 0xff101812);
  while (m.raster.character < 6)
    robotron_run(&m, 1);
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[0] == 0xff83e7a0 && pixels[w] == 0xff101812 &&
         pixels[w + 1] == 0xff83e7a0);
  m.cursor[0] = 0;
  m.cursor[1] = 0;
  m.crtc[3] = 0x60; // steady block cursor
  while (m.raster.character < 12)
    robotron_run(&m, 1);
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[2 * w] == 0xff101812 && pixels[2 * w + 1] == 0xff83e7a0);
  assert(pixels[0] == 0xff83e7a0 && pixels[w + 1] == 0xff83e7a0);
  robotron *saved = malloc(sizeof(m));
  assert(saved);
  *saved = m;
  robotron_run(&m, clocks_to_ticks(11));
  robotron_raster expected = m.raster;
  m = *saved;
  robotron_rebind(&m);
  robotron_run(&m, clocks_to_ticks(11));
  assert(!memcmp(&expected, &m.raster, sizeof(expected)));
  free(saved);
  // Stop display and a fresh Start must not expose retained previous-frame
  // lines.
  robotron_output(&m, 0x19, 0x40);
  robotron_output(&m, 0x19, 0x20);
  robotron_video(&m, pixels, &w, &h);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
}

/* Exercise the port-programmed geometry and the rational-clock boundaries.
 * Spaced rows double the row period, not the number of glyph-ROM lines. */
static void display_boundary_cases(void) {
  unsigned w, h;
  init();
  m.crtc[0] = 0x83;
  m.crtc[1] = 1;
  m.crtc[2] = 3;
  m.crtc[3] = 0x70;
  m.cursor[0] = 255;
  memset(m.vram, 'A', 8);
  for (unsigned y = 0; y < 4; y++)
    m.chargen[y * 128 + 'A'] = 0x80;
  robotron_output(&m, 0x19, 0x20);
  robotron_run(&m, clocks_to_ticks(48));
  assert(m.raster.row == 0 && m.raster.character == 0);
  robotron_run(&m, clocks_to_ticks(24));
  assert(m.raster.row == 0 && m.raster.character == 24);
  robotron_video(&m, pixels, &w, &h);
  assert(w == 32 && h == 8);
  for (unsigned y = 0; y < 4; y++)
    assert(pixels[y * w] == 0xff83e7a0);
  memset(m.chargen, 0, sizeof(m.chargen));
  robotron_run(&m, clocks_to_ticks(23));
  assert(m.raster.row == 0);
  robotron_video(&m, pixels, &w, &h);
  for (unsigned y = 0; y < 4; y++)
    assert(pixels[y * w] == 0xff83e7a0);
  robotron_run(&m, clocks_to_ticks(1));
  assert(m.raster.row == 1);

  /* Reset/program/start in the middle of scanout: new dimensions must never
   * expose old retained pixels, even before the first new row is available. */
  robotron_output(&m, 0x19, 0);
  const uint8_t geometry[] = {1, 0, 1, 0x70};
  send(0x18, geometry, 4);
  robotron_output(&m, 0x19, 0x20);
  robotron_video(&m, pixels, &w, &h);
  assert(w == 16 && h == 2);
  for (unsigned i = 0; i < w * h; i++)
    assert(pixels[i] == 0xff101812);
  m.chargen['A'] = 0x40;
  m.chargen[128 + 'A'] = 0x20;
  robotron_run(&m, clocks_to_ticks(8));
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[1] == 0xff83e7a0 && pixels[w + 2] == 0xff101812);
  robotron_run(&m, clocks_to_ticks(4));
  robotron_video(&m, pixels, &w, &h);
  assert(pixels[w + 2] == 0xff83e7a0);

  /* Attribute blink changes at frame 32; the next line still samples its
   * glyph at its own boundary. Cursor blink switches at frame 16. */
  for (unsigned cursor = 0; cursor < 2; cursor++) {
    init();
    m.crtc[0] = 3;
    m.crtc[1] = 1;
    m.crtc[2] = 1;
    m.crtc[3] = cursor ? 0x40 : 0x70;
    m.cursor[0] = cursor ? 1 : 255;
    m.cursor[1] = 0;
    memset(m.vram, 'A', 8);
    if (!cursor)
      m.vram[0] = 0x82;
    m.chargen['A'] = m.chargen[128 + 'A'] = 0x80;
    m.raster.frames = cursor ? 14 : 30;
    robotron_output(&m, 0x19, 0x20);
    robotron_run(&m, clocks_to_ticks(18)); // frame15/31, row0 line1
    assert(m.raster.frames == (cursor ? 15u : 31u));
    assert(m.raster.scanout[0].pixels[1][0] == (cursor ? 0x7f : 0));
    assert(m.raster.scanout[0].pixels[1][1] == (cursor ? 0x7f : 0));
    robotron_run(&m, clocks_to_ticks(30)); // next frame row0 line0
    assert(m.raster.frames == (cursor ? 16u : 32u));
    assert(m.raster.scanout[0].pixels[1][0] == 0x80);
    assert(m.raster.scanout[0].pixels[1][1] == (cursor ? 0x7f : 0));
    robotron_run(&m, clocks_to_ticks(6));
    assert(m.raster.scanout[0].pixels[1][1] == 0x80);
  }
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
  assert(m.rx.count == 3 && (m.rx.fifo_errors[(m.rx.read+2)%3] & 0x20));
  for (unsigned i = 0; i < 3; i++)
    assert(robotron_input(&m, 0x0c) == (i == 2 ? 3 : i));
  robotron_output(&m, 0x0e, 0x30);
  assert(!m.rx.errors);
  serial_byte(0x55, 0);
  assert(m.rx.fifo_errors[m.rx.read] & 0x40);
  robotron_output(&m, 0x0e, 0x18);
  assert(!m.rx.count && !m.rx.errors);
  serial_byte(1, 1);
  assert(!m.rx.count); /* receiver disabled after reset */
  /* A tiny original ROM exercises the matrix/LED strobes through the CPU. */
  uint8_t rom[2048] = {0x01, 0x00, 0x40,
                       0xed, 0x78, 0x76}; /* LD BC,4000; IN A,(C); HALT */
  robotron_keyboard k;
  robotron_keyboard_init(&k, rom, NULL, NULL);
  for (unsigned i = 0; i < 1000; i++)
    robotron_keyboard_tick(&k);
  assert(k.leds == 2);
  /* Same address preserves a D latch; both address bits can be set together.
   * A15-high matrix reads must leave the lamps alone. */
  k.cpu.pins = 0;
  k.cpu.bus.input(&k, 0x4000);
  assert(k.leds == 2);
  k.cpu.bus.input(&k, 0x6000);
  assert(k.leds == 3);
  k.cpu.bus.input(&k, 0x8100);
  assert(k.leds == 3);
  k.cpu.bus.input(&k, 0x2000);
  assert(k.leds == 1);
  k.cpu.bus.input(&k, 0x0000);
  assert(k.leds == 0);
  k.cpu.bus.output(&k, 0x6000, 0);
  assert(k.leds == 3);
  k.cpu.bus.output(&k, 0x0000, 0);
  assert(k.leds == 0);
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
static void printer_readiness(void) {
  init();
  m.sio_regs[0][4] = 4;
  m.sio_regs[0][5] = 0x68;
  m.sio_regs[0][3] = 32;
  for (unsigned state = 1; state <= 3; state++) {
    robotron_printer_state(&m, state);
    assert(!(robotron_input(&m, 0x0e) & 32));
    robotron_output(&m, 0x0c, 'A');
    for (unsigned i = 0; i < 20; i++)
      robotron_printer_clock(&m);
    assert(m.tx_full && !m.tx_clocks);
    robotron_printer_state(&m, 0);
    for (unsigned i = 0; i < 10; i++)
      robotron_printer_clock(&m);
    assert(m.printer_size == state);
  }
  robotron_output(&m, 0x0c, 'B');
  robotron_printer_clock(&m);
  robotron_printer_state(&m, 2);
  for (unsigned i = 0; i < 9; i++)
    robotron_printer_clock(&m);
  assert(m.printer_size == 4 && m.printer[3] == 'B');
  m.sio_regs[0][3] = 0;
  robotron_output(&m, 0x0c, 'C');
  for (unsigned i = 0; i < 10; i++)
    robotron_printer_clock(&m);
  assert(m.printer_size == 4 && m.printer_dropped == 1);
  m.sio_regs[0][1] = 1;
  m.sio_regs[1][1] = 4;
  m.sio_regs[1][2] = 0x80;
  robotron_printer_state(&m, 0);
  assert(m.printer_ext_pending);
  assert(m.cpu.bus.ack(&m) == 0x8a);
  assert(m.cpu.bus.ack(&m) == 0xff);
  robotron_sio_control(&m, 0, 0x10);
  robotron_sio_control(&m, 0, 0x38);
  assert(!m.printer_ext_service && !m.printer_ext_pending);
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

/* Abort formatting before/after the first complete data field. Preserve the
 * allocated EDSK and unrelated drive; never manufacture a partly written ID. */
static void write_interruptions(void) {
  const unsigned sizes[] = {1, 1, 1}, prefixes[] = {1, 128, 255};
  static uint8_t other[819200];
  for (unsigned action = 0; action < 3; action++)
    for (unsigned n = 0; n < 3; n++) {
      unsigned length; uint8_t *b = layout(sizes, 3, &length);
      init(); memset(other, 0x68, sizeof(other));
      assert(!robotron_disk(&m, dac_memory_storage(b,length,1),1));
      assert(!robotron_disk_unit(&m,1,dac_memory_storage(other,sizeof(other),1),1));
      data_command(0x45,7,1,7);wait_data();
      for (unsigned i=0;i<prefixes[n];i++) {
        if(m.fdc.ready_at>m.cpu.cycles)robotron_run(&m,(unsigned)(m.fdc.ready_at-m.cpu.cycles));
        robotron_output(&m,0x1d,0xa6);
      }
      if(action==0)m.motor|=128;
      else if(action==1)robotron_output(&m,0x20,0);
      else robotron_drive_door(&m,0,1);
      robotron_run(&m,1);
      assert(m.fdc.phase!=2);
      for(unsigned i=0;i<256;i++)assert(b[512+i]==(i<prefixes[n]?0xa6:0x31));
      assert(b[256+0x1c]==0x20 && b[256+0x1d]==0x20);
      for(unsigned i=768;i<1280;i++)assert(b[i]==(i<1024?0x32:0x33));
      for(unsigned i=0;i<sizeof(other);i++)assert(other[i]==0x68);
      assert(!robotron_disk_validate(dac_memory_storage(b,length,0)));
      free(b);
    }
}

static void format_interruptions(void) {
  const unsigned sizes[] = {1, 1, 1};
  const uint8_t fmt[] = {0x4d, 0, 1, 3, 27, 0xe9};
  const uint8_t id[] = {0, 0, 2, 1};
  static uint8_t other[819200];
  for (unsigned completed = 0; completed < 2; completed++)
    for (unsigned action = 0; action < 3; action++) {
      unsigned length;
      uint8_t *b = layout(sizes, 3, &length);
      init();
      memset(other, 0x68, sizeof(other));
      assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
      assert(!robotron_disk_unit(
          &m, 1, dac_memory_storage(other, sizeof(other), 1), 1));
      send(0x1d, fmt, sizeof(fmt));
      wait_data();
      for (unsigned i = 0; i < 4; i++) {
        if (m.fdc.ready_at > m.cpu.cycles)
          robotron_run(&m, (unsigned)(m.fdc.ready_at - m.cpu.cycles));
        robotron_output(&m, 0x1d, id[i]);
      }
      assert(m.fdc.search == 6);
      if (completed)
        wait_data();
      if (action == 0)
        m.motor |= 128;
      else if (action == 1)
        robotron_output(&m, 0x20, 0);
      else
        robotron_drive_door(&m, 0, 1);
      robotron_run(&m, 1);
      assert(m.fdc.phase != 2);
      assert(m.disk_writes == completed);
      for (unsigned i = 0; i < 256; i++) {
        assert(b[512 + i] == (completed ? 0xe9 : 0x31));
        assert(b[768 + i] == 0x32 && b[1024 + i] == 0x33);
      }
      for (unsigned i = 0; i < sizeof(other); i++)
        assert(other[i] == 0x68);
      assert(!robotron_disk_validate(dac_memory_storage(b, length, 0)));
      free(b);
    }
  /* Unsupported Read Track size mismatch is explicit and bounded. Ordinary
   * sector reads on mixed-size tracks remain covered separately. */
  unsigned length;
  const unsigned mixed[] = {0, 1};
  uint8_t *b = layout(mixed, 2, &length);
  init();
  assert(!robotron_disk(&m, dac_memory_storage(b, length, 1), 1));
  data_command(0x42, 7, 1, 2);
  for (unsigned t = 0; t < 3 * ROBOTRON_REVOLUTION_TICKS && m.fdc.phase == 2;
       t++)
    robotron_run(&m, 1);
  assert(m.fdc.phase == 1 && m.fdc.result[1] == 4 && !m.disk_reads);
  free(b);
}

static void drive_door(void) {
  robotron_init(&m);
  uint8_t *bytes = calloc(1, 819200);
  assert(bytes);
  assert(!robotron_disk(&m, dac_memory_storage(bytes, 819200, 1), 1));
  m.motor = 0;
  m.drive[0].ready = m.drive[0].loaded = 1;
  assert(robotron_drive_ready(&m, 0));
  robotron_drive_door(&m, 0, 1);
  assert(!robotron_drive_ready(&m, 0) && !m.drive[0].loaded);
  assert(m.disk.storage.read && !m.drive[1].door_open);
  robotron_run(&m, 2000000);
  assert(!robotron_drive_ready(&m, 0) && !m.drive[0].index_count);
  robotron_drive_door(&m, 0, 0);
  assert(!robotron_drive_ready(&m, 0));
  robotron_run(&m, 2000000);
  assert(robotron_drive_ready(&m, 0));
  free(bytes);
}
static void v24_test_clock(void) {
  for (unsigned i = 0; i < 16; i++)
    robotron_v24_peer_tick(&m);
  robotron_v24_clock(&m);
}
static void v24(void) {
  init();
  robotron_output(&m, 9, 7);
  robotron_output(&m, 9, 1);
  m.v24.signals = 3;
  const uint8_t setup[] = {3, 0xc1, 4, 0x44, 5, 0xea, 1, 0x10, 2, 0x60};
  send(0x0f, setup, sizeof(setup));
  m.v24.input[0] = 0xa5;
  m.v24.count = 1;
  for (unsigned i = 0; i < 160; i++)
    v24_test_clock();
  assert(m.rx_b.count == 1 && !m.rx.count && !m.rx_b.errors);
  assert(robotron_input(&m, 0x0d) == 0xa5 && !m.rx_b.count);
  robotron_output(&m, 0x0d, 0x5a);
  for (unsigned i = 0; i < 159; i++)
    v24_test_clock();
  assert(!m.v24.size);
  v24_test_clock();
  assert(m.v24.size == 1 && m.v24.output[0] == 0x5a);
  assert(m.v24.decoded_size == 1 && m.v24.decoded[0] == 0x5a &&
         !m.v24.decoder.errors);
  /* CTC0 channel 1, not frame/render callbacks, drives the internal route. */
  robotron_output(&m, 9, 7);
  robotron_output(&m, 9, 1);
  robotron_output(&m, 0x0d, 0x33);
  robotron_run(&m, 2560);
  assert(m.v24.size == 2 && m.v24.output[1] == 0x33);
  m.v24.signals = 7;
  m.sio_regs[1][5] &= ~2;
  m.v24.input[m.v24.read] = 0x44;
  m.v24.count = 1;
  for (unsigned i = 0; i < 200; i++)
    v24_test_clock();
  assert(m.v24.count == 1);
  m.sio_regs[1][5] |= 2;
  for (unsigned i = 0; i < 160; i++)
    v24_test_clock();
  assert(robotron_input(&m, 0x0d) == 0x44);
  m.sio_regs[1][3] |= 32;
  m.v24.signals = 2;
  robotron_output(&m, 0x0d, 0x77);
  for (unsigned i = 0; i < 200; i++)
    v24_test_clock();
  assert(m.v24.full && m.v24.size == 2);
  m.v24.signals = 3;
  for (unsigned i = 0; i < 160; i++)
    v24_test_clock();
  assert(m.v24.output[2] == 0x77);
  /* FIFO overrun is visible; reading B does not consume keyboard A. */
  for (unsigned i = 0; i < 4; i++)
    m.v24.input[(m.v24.read + i) % 65536] = (uint8_t)i;
  m.v24.count = 4;
  for (unsigned i = 0; i < 640; i++)
    v24_test_clock();
  assert(m.rx_b.count == 3 && (m.rx_b.fifo_errors[(m.rx_b.read+2)%3] & 32));
  robotron_output(&m, 0x0f, 1);
  assert(!(robotron_input(&m, 0x0f) & 32));
  robotron_output(&m, 0x0f, 0x30);
  assert(!m.rx_b.errors);
  assert(robotron_input(&m, 0x0d) == 0);
  assert(robotron_input(&m, 0x0d) == 1);
  assert(robotron_input(&m, 0x0d) == 3);
  assert(m.rx_b.errors & 32);
  robotron_output(&m, 0x0f, 0x30);
  m.sio_regs[1][1] = 0x14;
  m.rx_b.pending = 1;
  assert(m.cpu.bus.ack(&m) == 0x64);
  robotron_output(&m, 0x0f, 0x38);
  assert(!m.rx_b.in_service);
}

static void v24_independent_peer(void) {
  init();
  robotron_output(&m, 9, 7);
  robotron_output(&m, 9, 13);
  const uint8_t setup[] = {3, 0xc1, 4, 0x44, 5, 0xea, 1, 0x15, 2, 0x60};
  send(15, setup, sizeof(setup));
  m.v24.signals = 3;
  m.v24.peer_baud = 1200;
  m.v24.peer_format = 0x208;
  m.v24.input[0] = 0xa5;
  m.v24.count = 1;
  robotron_run(&m, 40000);
  assert(m.rx_b.count == 1 && !m.rx_b.errors);
  assert(robotron_input(&m, 13) == 0xa5);
  /* Peer odd parity versus guest even parity. */
  m.sio_regs[1][4] = 0x47;
  m.v24.peer_format = 0x218;
  m.v24.input[m.v24.read] = 0x55;
  m.v24.count = 1;
  robotron_run(&m, 40000);
  assert(m.rx_b.errors & 0x10);
  assert(m.cpu.bus.ack(&m) == 0x66);
  robotron_output(&m, 14, 0x38);
  assert(!m.rx_b.in_service);
  robotron_output(&m, 15, 0x30);
  robotron_input(&m, 13);
  assert(!m.rx_b.errors);
  /* External status is latched until Reset External/Status. */
  robotron_v24_signals(&m, 2);
  assert(m.v24.ext_pending && !(robotron_input(&m, 15) & 32));
  robotron_v24_signals(&m, 3);
  assert(!(robotron_input(&m, 15) & 32));
  assert(m.cpu.bus.ack(&m) == 0x62);
  robotron_output(&m, 15, 0x10);
  assert(robotron_input(&m, 15) & 32);
  robotron_output(&m, 14, 0x38);
  assert(!m.v24.ext_service);
  /* Exact 21 half-cells for 8N1.5, including x1 adaptive clocking. */
  m.v24.peer_baud = 0;
  m.sio_regs[1][4] = 8;
  m.v24.input[m.v24.read] = 0;
  m.v24.count = 1;
  for (unsigned n = 0; n < 2183; n++)
    robotron_v24_peer_tick(&m);
  assert(m.v24.bits == 1);
  robotron_v24_peer_tick(&m);
  assert(!m.v24.bits);
}

static void dma_modes_restart(void) {
  init();
  m.ram[0x4000] = 0x5a;
  dma(0x4000, 0x5000, 2, 0x10, 0x10);
  robotron_output(&m, 0, 0xa2); /* WR5 auto restart */
  robotron_output(&m, 0, 0xb3);
  robotron_output(&m, 0, 0x87);
  robotron_run(&m, 12);
  assert(m.dma.enabled && m.dma.remaining == 2 && m.dma.run_a == 0x4000 &&
         !m.dma.transferred);
  robotron_output(&m, 0, 0xc3);
  assert(!m.dma.auto_restart);
  for (unsigned mode = 0; mode < 3; mode++) {
    init();
    dma(0x4000, 0x5000, 4, 0x10, 0x10);
    robotron_output(&m, 0, 0x81 | (mode << 5));
    robotron_output(&m, 0, 0xb3);
    robotron_output(&m, 0, 0x87);
    robotron_run(&m, 6);
    assert(m.dma.transferred == 1);
    m.dma.force_ready = 0;
    unsigned step = m.cpu.cpu.step;
    robotron_run(&m, 20);
    if (mode == 1)
      assert(m.cpu.cpu.step == step && m.dma.bus_owned);
    else
      assert(!m.dma.bus_owned);
  }
}
static void serial_peer_decoder(void) {
  init();
  robotron_output(&m, 9, 7);
  robotron_output(&m, 9, 13);
  m.sio_regs[1][4] = 0x47;
  m.sio_regs[1][5] = 0xea;
  m.v24.signals = 3;
  m.v24.peer_baud = 1200;
  m.v24.peer_format = 0x228;
  robotron_output(&m, 13, 0xa5);
  robotron_run(&m, 45000);
  assert(m.v24.decoded_size == 1 && m.v24.decoded[0] == 0xa5 &&
         !m.v24.decoder.errors);
  m.v24.peer_format = 0x218;
  robotron_output(&m, 13, 0x55);
  robotron_run(&m, 45000);
  assert(m.v24.decoded_size == 2 && (m.v24.decoder.errors & 16));
}
static void serial_break_lock(void) {
  init();
  m.sio_regs[1][3] = 0xc1;
  m.sio_regs[1][4] = 4;
  m.sio_regs[1][1] = 9;
  for (unsigned i = 0; i < 10; i++)
    robotron_v24_receive_clock(&m, 0);
  assert(m.v24.break_active && m.v24.ext_pending &&
         (robotron_v24_read(&m, 1) & 128));
  assert(m.rx_b.count == 1);
  robotron_v24_read(&m, 0);
  assert(m.rx_b.rx_locked && m.rx_b.count == 1);
  robotron_sio_control(&m, 1, 0x30);
  assert(!m.rx_b.rx_locked && !m.rx_b.count);
  robotron_sio_control(&m, 1, 0x10);
  robotron_v24_receive_clock(&m, 1);
  assert(!m.v24.break_active && m.v24.ext_pending &&
         !(robotron_v24_read(&m, 1) & 128));
}
/* Bounded clock fixtures: no wall-clock waits, ROM boot or Verilog. */
static void serial_clock_domains(void) {
  for (unsigned selector = 0; selector < 4; selector++) {
    const unsigned divisors[] = {1, 16, 32, 64};
    unsigned clocks = (21 * divisors[selector] + 1) / 2;
    init();
    m.sio_regs[1][3] = 0xc1;
    m.sio_regs[1][4] = (selector << 6) | 8; /* 8N1.5 */
    m.sio_regs[1][5] = 0xea;
    m.v24.signals = 3;
    robotron_output(&m, 13, 0xa5);
    /* RX edges cannot consume the TX holding register. */
    for (unsigned i = 0; i < 128; i++)
      robotron_v24_receive_clock(&m, 1);
    assert(m.v24.full && !m.v24.size && !m.v24.tx_clocks);
    for (unsigned i = 1; i < clocks; i++)
      robotron_v24_transmit_clock(&m);
    assert(!m.v24.size && m.v24.tx_clocks == 1);
    robotron_v24_transmit_clock(&m);
    assert(m.v24.size == 1 && m.v24.output[0] == 0xa5);
    assert(!m.rx_b.count && !m.rx_b.phase);
    /* Printer uses the same documented frame length/divisors. */
    m.sio_regs[0][4] = (selector << 6) | 8;
    m.sio_regs[0][5] = 0xea;
    m.tx_holding = 0x5a;
    m.tx_full = 1;
    for (unsigned i = 1; i < clocks; i++)
      robotron_printer_clock(&m);
    assert(!m.printer_size && m.tx_clocks == 1);
    robotron_printer_clock(&m);
    assert(m.printer_size == 1 && m.printer[0] == 0x5a);
  }
  init();
  m.sio_regs[1][3] = 0xc1;
  m.sio_regs[1][4] = 4; /* Externally synchronized x1 samples. */
  m.sio_regs[1][5] = 0xea;
  m.v24.signals = 3;
  robotron_output(&m, 13, 0x42);
  robotron_v24_receive_clock(&m, 0);
  for (unsigned i = 0; i < 8; i++)
    robotron_v24_receive_clock(&m, (0xa5 >> i) & 1);
  robotron_v24_receive_clock(&m, 1);
  assert(m.rx_b.count == 1 && robotron_v24_read(&m, 0) == 0xa5);
  assert(m.v24.full && !m.v24.size); /* No TX edges supplied. */
}
static void serial_short_characters(void) {
  const unsigned widths[] = {5, 7, 6, 8}, divisors[] = {1, 16, 32, 64};
  for (unsigned channel = 0; channel < 2; channel++)
    for (unsigned selector = 0; selector < 4; selector++)
      for (unsigned width_code = 0; width_code < 4; width_code++)
        for (unsigned parity_mode = 0; parity_mode < 3; parity_mode++)
          for (unsigned sample = 0; sample < 2; sample++) {
            init();
            unsigned width = widths[width_code], div = divisors[selector];
            unsigned value = (sample ? 0x15 : 0x02) & ((1u << width) - 1);
            unsigned parity = 0;
            for (unsigned bit = 0; bit < width; bit++) parity ^= value >> bit & 1;
            if (parity_mode == 1) parity ^= 1; /* odd */
            m.sio_regs[channel][3] = (width_code << 6) | 1;
            m.sio_regs[channel][4] = (selector << 6) | 4 |
                                    (parity_mode ? (parity_mode == 1 ? 1 : 3) : 0);
            unsigned frame = value << 1, bits = width + 1;
            if (parity_mode) frame |= parity << bits++;
            frame |= 1u << bits++;
            for (unsigned bit = 0; bit < bits; bit++)
              for (unsigned clock = 0; clock < div; clock++) {
                if (channel) robotron_v24_receive_clock(&m, frame >> bit & 1);
                else robotron_serial_clock(&m, frame >> bit & 1);
              }
            unsigned expected = value | (0xffu << width);
            if (parity_mode && width < 8)
              expected = (expected & ~(1u << width)) | (parity << width);
            robotron_sio_rx *rx = channel ? &m.rx_b : &m.rx;
            assert(rx->count == 1 && !rx->errors);
            assert((channel ? robotron_v24_read(&m, 0) : robotron_sio_read(&m, 0)) == (expected & 255));
          }
  /* Padding ones must not suppress BREAK detection for a short zero frame. */
  init();
  m.sio_regs[1][3] = 1;
  m.sio_regs[1][4] = 4;
  for (unsigned i = 0; i < 7; i++) robotron_v24_receive_clock(&m, 0);
  assert(m.v24.break_active);
}
/* UM008101 pp.236–237: framing follows the FIFO; overflow replaces tail.
 * Exercise both channels, including first-character error lock/reset. */
static void serial_error_fifo(void) {
  for (unsigned ch = 0; ch < 2; ch++) {
    init();
    m.sio_regs[ch][3] = 0xc1;
    m.sio_regs[ch][4] = 4;
    void (*clock)(robotron *, unsigned) = ch ? robotron_v24_receive_clock : NULL;
    for (unsigned n = 0; n < 4; n++) {
      unsigned value = 0x51 + n;
      for (unsigned bit = 0; bit < 10; bit++) {
        unsigned level = bit == 0 ? 0 : bit == 9 ? n != 1 : (value >> (bit-1)) & 1;
        if (clock) clock(&m, level); else robotron_serial_clock(&m, level);
      }
    }
    robotron_sio_rx *rx = ch ? &m.rx_b : &m.rx;
    assert(rx->count == 3 && (rx->fifo_errors[(rx->read+2)%3] & 0x20));
    robotron_sio_control(&m, ch, 0x30);
    for (unsigned n = 0; n < 3; n++) {
      robotron_sio_control(&m, ch, 1);
      unsigned status = ch ? robotron_v24_read(&m, 1) : robotron_sio_read(&m, 1);
      assert((status & 0x70) == (n == 1 ? 0x40 : n == 2 ? 0x20 : 0));
      m.sio_regs[ch][1] = n == 1 ? 8 : 0;
      unsigned value = ch ? robotron_v24_read(&m, 0) : robotron_sio_read(&m, 0);
      assert(value == (n == 2 ? 0x54 : 0x51 + n));
      if (n == 1) {
        assert(rx->rx_locked && rx->count == 2);
        robotron_sio_control(&m, ch, 0x30);
        assert(!rx->rx_locked && rx->count == 1);
      }
    }
    assert(!rx->count);
  }
  /* A high parity bit interrupts a low frame, including eight-bit words. */
  for (unsigned width = 7; width <= 8; width++) {
    init(); m.sio_regs[1][3] = width == 7 ? 0x41 : 0xc1;
    m.sio_regs[1][4] = 5;
    for (unsigned i = 0; i <= width; i++) robotron_v24_receive_clock(&m, 0);
    robotron_v24_receive_clock(&m, 1);
    robotron_v24_receive_clock(&m, 0);
    assert(!m.v24.break_active && m.rx_b.count == 1);
    assert(m.rx_b.fifo_errors[0] == 0x40);
  }
}
static void serial_error_recovery(void) {
  const unsigned divisors[] = {16,32,64};
  for(unsigned ch=0;ch<2;ch++)for(unsigned n=0;n<3;n++){
    init();unsigned div=divisors[n];
    m.sio_regs[ch][3]=0xc1;m.sio_regs[ch][4]=((n+1)<<6)|4;
    m.sio_regs[ch][1]=8;
    // Nonzero data avoids BREAK; low stop incurs a half-bit recovery interval.
    for(unsigned bit=0;bit<10;bit++)for(unsigned t=0;t<div;t++){
      unsigned level=bit==1;
      if(ch)robotron_v24_receive_clock(&m,level);else robotron_serial_clock(&m,level);
    }
    robotron_sio_rx *rx=ch?&m.rx_b:&m.rx;
    assert(rx->phase==5&&rx->wait==1&&rx->count==1);
    if(ch)robotron_v24_receive_clock(&m,1);else robotron_serial_clock(&m,1);
    assert(!rx->phase&&rx->count==1&&rx->errors==0x40);
    // Error reset advances the locked error even without a prior data read.
    robotron_sio_control(&m,ch,0x30);assert(!rx->count&&!rx->errors);
    rx->errors=0x10;
    m.sio_regs[ch][1]=0x10;assert(robotron_sio_special(&m,ch)==0x10);
    m.sio_regs[ch][1]=0x18;assert(!robotron_sio_special(&m,ch));
  }
}
static void serial_explicit_edges(void) {
  const unsigned divisors[] = {1, 16, 32, 64};
  for (unsigned channel = 0; channel < 2; channel++)
    for (unsigned selector = 0; selector < 4; selector++)
      for (unsigned stop = 1; stop <= 3; stop++) {
        init();
        m.sio_regs[channel][4] = (selector << 6) | (stop << 2);
        m.sio_regs[channel][5] = 0x68;
        m.v24.signals = 3;
        robotron_output(&m, 12 + channel, 0xa5);
        robotron_serial_edge(&m, channel, 1, 1, 1);
        assert(channel ? m.v24.full : m.tx_full);   /* rising cannot start */
        robotron_serial_edge(&m, channel, 1, 0, 1); /* frame starts */
        unsigned halves = (18 + stop + 1) * divisors[selector];
        for (unsigned i = 1; i < halves; i++) {
          robotron_serial_edge(&m, channel, 1, i & 1, 1);
          robotron_serial_edge(&m, channel, 1, i & 1,
                               1); /* no duplicate edge */
          assert(!(channel ? m.v24.size : m.printer_size));
        }
        assert((channel ? m.v24.tx_halves : m.tx_halves) == 1);
        robotron_serial_edge(&m, channel, 1, halves & 1, 1);
        assert((channel ? m.v24.size : m.printer_size) == 1);
        assert((channel ? m.v24.output[0] : m.printer[0]) == 0xa5);
        assert(!m.rx_b.count && !m.rx.count);
      }
  init();
  m.sio_regs[1][3] = 0xc1;
  m.sio_regs[1][4] = 4;
  /* x1 external RX synchronization: falling edges cannot sample. */
  const unsigned frame = (0xa5u << 1) | (1u << 9);
  for (unsigned i = 0; i < 10; i++) {
    robotron_serial_edge(&m, 1, 0, 0, !(frame >> i & 1));
    robotron_serial_edge(&m, 1, 0, 1, frame >> i & 1);
  }
  assert(m.rx_b.count == 1 && robotron_v24_read(&m, 0) == 0xa5);
  /* WR5 disabling transmission must not strand an active printer frame. */
  m.sio_regs[0][4] = 8;
  m.sio_regs[0][5] = 0x68;
  robotron_output(&m, 12, 0x5a);
  robotron_serial_edge(&m, 0, 1, 1, 1);
  robotron_serial_edge(&m, 0, 1, 0, 1);
  m.sio_regs[0][5] &= ~8;
  for (unsigned i = 1; i <= 21; i++)
    robotron_serial_edge(&m, 0, 1, i & 1, 1);
  assert(m.printer_size == 1 && m.printer[0] == 0x5a);
  robotron_sio_control(&m, 0, 0x18);
  assert(!m.tx_halves && !m.serial_levels[1]);
}
int main(void) {
  serial_error_recovery();
  serial_error_fifo();
  serial_short_characters();
  serial_explicit_edges();
  serial_clock_domains();
  dma_modes_restart();
  serial_break_lock();
  serial_peer_decoder();
  v24();
  v24_independent_peer();
  drive_door();
  floppy_mechanics_and_deadlines();
  floppy_dsk();
  floppy_layout_commands();
  transmitter_interrupt();
  two_drives_format();
  write_interruptions();
  format_interruptions();
  printer();
  printer_readiness();
  keyboard_serial();
  floppy_seek();
  floppy_rotation();
  dma_memory();
  dma_phases();
  dma_search_wait_reset();
  floppy_completion();
  interrupt_chain();
  timer_cascade();
  display();
  display_fifo();
  display_schedule();
  display_latched_rows();
  display_byte_fetch();
  display_scanlines();
  display_boundary_cases();
  puts("PASS Robotron DMA/RDY/TC, FDC reset/status, daisy-chain/RETI, "
       "CRTC/attributes/cursor");
}
