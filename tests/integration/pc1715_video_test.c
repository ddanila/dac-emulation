#include "../../common/runtime/session.h"
#include "../../machines/robotron1715/pc1715.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void wr(pc1715 *m, unsigned a, unsigned d) {
  assert(pc1715_video_write(m, a, d));
}
static uint8_t status(pc1715 *m) {
  uint8_t d;
  assert(pc1715_video_read(m, 0x1b, &d));
  return d;
}
static void configure(pc1715 *m, unsigned flags) {
  wr(m, 0x1b, 0);
  wr(m, 0x1a, 79);
  wr(m, 0x18, 0x57);
  wr(m, 0x1a, 0xbb);
  wr(m, 0x18, flags | 13);
  wr(m, 0x19, 0x80);
  wr(m, 0x18, 255);
  wr(m, 0x18, 255);
  wr(m, 0x22, 31);
  wr(m, 0x19, 0x23);
}
static void run(pc1715 *m) { pc1715_run(m, PC1715_CLOCK_HZ / 20); }
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
  memset(m->ram + 0xf800, 1, 2048);
  configure(m, 0);
  run(m);
  assert(m->video.pixels[0] == 0xffaaaaaa);
  assert(m->video.pixels[1] == 0xff000000);
  assert(m->video.pixels[641] == 0xffaaaaaa);
  assert(m->video.pixels[640] == 0xff000000);
  assert(m->video.fetches > 1920 && !m->video.underruns);
  assert(status(m) & 32);
  assert(!(status(m) & 32));
  wr(m, 0x23, 31 | 64);
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
  wr(m, 0x22, 31);
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
    assert(m->video.pixels[11 * 640 + x] == 0xffaaaaaa);
  /* FIFO overflow on seventeenth invisible attribute, sticky until status read.
   */
  for (unsigned i = 0; i < 17; i++) {
    m->ram[0xf800 + 2 * i] = 0x80;
    m->ram[0xf801 + 2 * i] = 1;
  }
  configure(m, 0);
  run(m);
  assert(m->video.overflows && (status(m) & 1));
  assert(!(status(m) & 1));
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
