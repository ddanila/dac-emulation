#ifndef DAC_PC1715_VIDEO_H
#define DAC_PC1715_VIDEO_H
#include <stdint.h>
/* Optional ordinary-PC1715 8275 + refresh-slot display fetch. Fixed capture
 * canvas is 80 x 24 x (8 x 12); register timing remains programmable. */
typedef struct {
  unsigned enabled;
  uint8_t glyphs[4096];
  void *user;
  void (*signal)(void *, uint64_t dot, unsigned video, unsigned intensity,
                 unsigned bsync, unsigned hrtc, unsigned vrtc);
  uint8_t reg[6], status, pos, end, latch, dma;
  unsigned fraction, column, line, row, stream, running, preset;
  unsigned fetch_col, fifo_count, fifo_next, fetching, stop, field;
  uint8_t codes[80], fifo[16], chars[80], attrs[80], blank[80];
  unsigned refresh, row_valid, clocked, primed, vsync, burst, fetch_wait;
  uint64_t frames, dots, fetches, underruns, overflows;
  uint32_t pixels[640 * 288];
} pc1715_video;
#endif
