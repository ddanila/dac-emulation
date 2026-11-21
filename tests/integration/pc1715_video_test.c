#include "../../common/runtime/session.h"
#include "../../machines/robotron1715/pc1715.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void wr(pc1715 *m, unsigned a, unsigned d) {
  assert(pc1715_video_write(m, a, d));
}
static void configure_lines(pc1715 *m, unsigned flags, unsigned lines) {
  wr(m, 0x1b, 0);
  wr(m, 0x1a, 79);
  wr(m, 0x18, 0x57);
  wr(m, 0x1a, lines);
  wr(m, 0x18, flags | 13);
  wr(m, 0x19, 0x80);
  wr(m, 0x18, 255);
  wr(m, 0x18, 255);
  wr(m, 0x34, 0x3e);
  wr(m, 0x19, 0x23);
}
static void configure(pc1715 *m, unsigned flags) { configure_lines(m, flags, 0x6b); }
static void run(pc1715 *m) { pc1715_run(m, PC1715_CLOCK_HZ / 20); }
static unsigned floppy_writes, floppy_waits;
static int card_wait(void *p, uint16_t a, int writing) {
  (void)p;
  if (writing && (a & 0xfc) == 0x20) floppy_waits++;
  return 0;
}
static void card_write(void *p, uint16_t a, uint8_t d) {
  (void)p;
  assert((a & 0xfc) == 0x20 && d == 0xef);
  floppy_writes++;
}
static uint64_t signals, lastdot;
static unsigned pulses, previous = 1;
static void observe_signal(void *p, uint64_t dot, unsigned lit, unsigned high,
                           unsigned sync, unsigned h, unsigned v) {
  (void)p;
  (void)lit;
  (void)high;
  (void)v;
  assert(dot == lastdot++);
  signals++;
  if (!sync && previous && h)
    pulses++;
  previous = sync;
}
int main(void) {
  pc1715 *m = calloc(1, sizeof(*m));
  uint8_t glyphs[4096] = {0}, rom[2048] = {0};
  /* HALT is useful here: it still generates CPU M1/refresh opportunities. */
  rom[0] = 0x76;
  pc1715_init(m);
  assert(pc1715_load(m, rom, 2048) == 0);
  glyphs[1] = 0x80;
  glyphs[128 + 1] = 0x40;
  glyphs[2048 + 1] = 0x01;
  assert(pc1715_video_load(m, glyphs, 4096) == 0);
  /* Service manual pp.15-16: KRFD=20..23, BWSCS=34..37.
   * Sheet 2 A23.2/A22.4/X12: D1..D5 -> AB11..15, D0 unused at 80 columns.
   * Check every block and every alias independently of firmware constants. */
  for (unsigned block = 0; block < 32; block++) {
    pc1715_reset(m);
    memset(m->ram, 0, sizeof m->ram);
    memset(m->ram + block * 2048, 1, 2048);
    configure(m, 0);
    wr(m, 0xab34 | (block & 3), (block << 1) | (block & 1));
    for (unsigned a = 0x20; a <= 0x23; a++)
      assert(!pc1715_video_write(m, a, 0xef));
    assert(m->video.latch == ((block << 1) | (block & 1)));
    run(m);
    assert(m->video.pixels[0] == 0xffaaaaaa);
    assert(m->video.pixels[1] == 0xff000000);
    assert(!m->video.underruns);
  }
  /* With video enabled, CPU I/O still reaches the floppy card and its WAIT
   * callback. Video must not swallow KRFD writes or change the screen bank. */
  pc1715_reset(m);
  const uint8_t program[] = {0x3e,0xef,0xd3,0x20,0xd3,0x21,
                            0xd3,0x22,0xd3,0x23,0x76};
  memcpy(m->rom, program, sizeof program);
  pc1715_card card = {.wait=card_wait, .write=card_write};
  pc1715_attach(m, &card);
  wr(m, 0x34, 0x3e);
  run(m);
  assert(floppy_writes == 4 && floppy_waits == 4 && m->video.latch == 0x3e);
  memset(&m->card, 0, sizeof m->card);
  memcpy(m->rom, rom, sizeof rom);
  pc1715_reset(m);
  memset(m->ram + 0xf800, 1, 2048);
  configure(m, 0);
  run(m);
  assert(m->video.pixels[0] == 0xffaaaaaa);
  assert(m->video.pixels[1] == 0xff000000);
  assert(m->video.pixels[641] == 0xffaaaaaa);
  assert(m->video.pixels[640] == 0xff000000);
  assert(m->video.fetches > 1920 && !m->video.underruns);
  assert(m->video.status & 32);
  /* CPU reads cannot observe/clear internal status through A23.1. */
  for (unsigned a = 0x18; a <= 0x1b; a++) {
    uint8_t value = 0xa5;
    assert(!pc1715_video_read(m, 0xab00 | a, &value));
    assert(value == 0xa5 && (m->video.status & 32));
  }
  const uint8_t read_program[] = {0xdb,0x19,0x32,0x00,0xf0,0x76};
  memcpy(m->rom, read_program, sizeof read_program);
  m->cpu.cpu.pc = 0;
  /* Reset CPU instruction state with the usual machine reset, then restart CRT. */
  pc1715_reset(m);
  configure(m, 0);
  run(m);
  assert(m->ram[0xf000] == 0xff && m->unclaimed_reads == 1);
  assert(m->video.status & 32);
  memcpy(m->rom, rom, sizeof rom);
  wr(m, 0x37, 0x3e | 64);
  run(m);
  assert(m->video.pixels[7] == 0xffaaaaaa && m->video.pixels[0] == 0xff000000);
  /* Invisible field consumes one FIFO byte but retains a visible character. */
  m->ram[0xf800] = 0x85;
  m->ram[0xf801] = 1;
  m->ram[0xf802] = 1;
  run(m);
  assert(m->video.pixels[0] == 0xffffffff); /* bank latch XOR GPA0 */
  assert(m->video.pixels[8] == 0xffffffff);
  /* Reverse field and visible-attribute blanking. */
  wr(m, 0x34, 0x3e);
  m->ram[0xf800] = 0x90;
  run(m);
  assert(m->video.pixels[0] == 0xff000000 && m->video.pixels[1] == 0xffaaaaaa);
  configure(m, 64);
  run(m);
  assert(m->video.pixels[0] == 0xff000000);
  /* Cursor underline is forced on, not XORed with existing white pixels. */
  memset(m->ram + 0xf800, 1, 2048);
  configure(m, 0x30);
  wr(m, 0x19, 0x80);
  wr(m, 0x18, 0);
  wr(m, 0x18, 0);
  run(m);
  for (unsigned x = 0; x < 8; x++)
    assert(m->video.pixels[6 * 640 + x] == 0xffaaaaaa);
  /* FIFO overflow on seventeenth invisible attribute; inspect internal state.
   */
  for (unsigned i = 0; i < 17; i++) {
    m->ram[0xf800 + 2 * i] = 0x80;
    m->ram[0xf801 + 2 * i] = 1;
  }
  configure(m, 0);
  run(m);
  assert(m->video.overflows && (m->video.status & 1));
  /* Independent boundary-line vectors: threshold 7/8 and BBh/6Bh.
   * Exercise both LC modes with white glyphs, then cursor/field LTEN and RVV. */
  for (unsigned y = 0; y < 16; y++) m->video.glyphs[y * 128 + 2] = 255;
  const unsigned line_settings[] = {0x6b, 0x7b, 0x8b, 0xbb};
  for (unsigned mode = 0; mode < 2; mode++) {
    for (unsigned k = 0; k < 4; k++) {
      pc1715_reset(m);
      memset(m->ram + 0xf800, 2, 2048);
      configure_lines(m, mode * 128, line_settings[k]);
      run(m);
      for (unsigned y = 0; y < 288; y++)
        for (unsigned x = 0; x < 640; x++) {
          unsigned suppressed = k >= 2 && (y % 12 == 0 || y % 12 == 11);
          assert(m->video.pixels[y * 640 + x] ==
                 (suppressed ? 0xff000000 : 0xffaaaaaa));
        }
      assert(!m->video.underruns && !m->video.overflows);
    }
  }
  /* LTEN is applied after VSP/RVV by A16.2: underline survives blanking. */
  configure_lines(m, 0x30, 0xbb);
  wr(m, 0x19, 0x80); wr(m, 0x18, 0); wr(m, 0x18, 0);
  run(m);
  assert(m->video.pixels[0] == 0xff000000);
  assert(m->video.pixels[11 * 640] == 0xffaaaaaa);
  assert(m->video.pixels[11 * 640 + 8] == 0xff000000);
  m->ram[0xf800] = 0xb0; /* underline + reverse, then a full-white glyph */
  m->ram[0xf801] = 2;
  configure_lines(m, 0, 0xbb);
  run(m);
  assert(m->video.pixels[0] == 0xff000000);
  assert(m->video.pixels[640] == 0xff000000);
  assert(m->video.pixels[11 * 640] == 0xffaaaaaa);
  /* Actual refresh slots gate DMA. Suppressing refresh must cause underrun. */
  pc1715_reset(m);
  configure(m, 0);
  for (unsigned i = 0; i < 5000; i++)
    pc1715_video_tick(m);
  assert(m->video.underruns && !m->video.fetches);
  /* Reset retains installed glyphs and observer, clears scanout/counters. */
  m->video.signal = observe_signal;
  pc1715_reset(m);
  assert(m->video.enabled && m->video.glyphs[1] == 0x80 &&
         m->video.signal == observe_signal);
  memset(m->ram + 0xf800, 1, 2048);
  configure(m, 0);
  run(m);
  assert(signals > 600000 && pulses > 600);
  assert(m->video.frames ==
         3); /* first partial blank row, then 2 full frames */
  assert(m->video.dots == signals);
  uint64_t before = m->video.dots;
  wr(m, 0x19, 0x40);
  run(m);
  assert(m->video.dots > before); /* STOP blanks VIDEO, keeps sync clocking. */
  for (unsigned i = 0; i < 640 * 288; i++)
    assert(m->video.pixels[i] == 0xff000000);
  dac_session *s = dac_create(3);
  assert(s);
  assert(dac_load(s, 0, rom, 2048) == 0);
  assert(!dac_video(s));
  assert(dac_load(s, 2, glyphs, 2048) < 0);
  assert(dac_load(s, 2, glyphs, 4096) == 0);
  assert(dac_width(s) == 640 && dac_height(s) == 288);
  assert(dac_video(s));
  assert(dac_power(s, 1) == 0);
  dac_run(s, 1000);
  assert(dac_video(s) && dac_width(s) == 640);
  assert(dac_reset(s) == 0);
  assert(dac_video(s) && dac_height(s) == 288);
  dac_destroy(s);
  free(m);
  puts("PASS PC1715 CRT registers, aliases, glyph wiring, attributes, FIFO, "
       "refresh DMA, timing, reset and session opt-in");
}
