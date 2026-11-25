/* Digital D54/D55 timing. Included by juku.c for legacy single-unit consumers.
 * 8253 counters count on CLK falling edges. D54 receives D40's 1 MHz;
 * D55.CLK0 receives D54.OUT0; D55.CLK1/2 receive D56.Q2_N. D56 is
 * retriggered by the rising edge of D54.OUT2 (5.04 us pulse).
 * CPU accesses remain instruction-granular; analog output and DRAM slot
 * contention are outside this model. No guest-program signatures are used. */
static uint32_t pit_decode(uint16_t v, unsigned bcd) {
  if (!v) return bcd ? 10000 : 65536;
  if (!bcd) return v;
  return (v & 15) + 10 * ((v >> 4) & 15) +
         100 * ((v >> 8) & 15) + 1000 * ((v >> 12) & 15);
}
static uint16_t pit_encoded(const pit_counter *p) {
  uint32_t n = p->counter;
  if (!p->bcd) return (uint16_t)n;
  n %= 10000;
  return (uint16_t)((n % 10) | (((n / 10) % 10) << 4) |
                    (((n / 100) % 10) << 8) | ((n / 1000) << 12));
}
static void pit_gate(pit_counter *p, uint8_t level) {
  if (level && !p->gate && p->armed) p->trigger = 1;
  p->gate = level;
  if (!level && (p->mode == 2 || p->mode == 3)) {
    p->output = 1;
    p->running = 0;
  }
}
static void pit_clock(pit_counter *p) {
  if (!p->armed) return;
  if (p->trigger && (p->mode == 1 || p->mode == 5 || p->mode == 2 || p->mode == 3)) {
    p->trigger = 0;
    p->counter = p->reload;
    p->running = 1;
    p->pending = 0;
    p->output = p->mode != 1;
    return;
  }
  p->trigger = 0;
  if (p->pending && (!(p->mode == 2 || p->mode == 3) || !p->running)) {
    p->pending = 0;
    p->counter = p->reload;
    p->running = 1;
    p->output = p->mode != 0;
    return;
  }
  if (!p->running || (!p->gate && p->mode != 1 && p->mode != 5)) return;
  switch (p->mode) {
  case 0: case 1:
    if (p->counter > 0 && --p->counter == 0) p->output = 1;
    else if (!p->counter) p->counter = p->bcd ? 9999 : 65535;
    break;
  case 2:
    if (!p->output) {
      p->counter = p->reload;
      p->pending = 0;
      p->output = 1;
    } else if (p->counter > 1 && --p->counter == 1) p->output = 0;
    break;
  case 3:
    /* Odd counts: first high clock decrements by one; the low half loads
     * N-1. Both remaining phases decrement by two (Intel mode-3 waveform). */
    if ((p->counter & 1) && p->output) p->counter--;
    else if (p->counter > 2) p->counter -= 2;
    else {
      p->output ^= 1;
      p->counter = p->reload - (!p->output && (p->reload & 1));
      p->pending = 0;
    }
    break;
  case 4: case 5:
    if (!p->output) { p->output = 1; p->running = 0; }
    else if (p->counter && --p->counter == 0) p->output = 0;
    break;
  }
}
static void video_outputs(juku *j, uint8_t out[6]) {
  for (unsigned i = 0; i < 6; ++i) out[i] = j->pit_counters[i / 3][i % 3].output;
}
static void video_end_line(juku_scanout *s) {
  if (!s->line_active) return;
  if (s->x > s->width) s->width = s->x;
  if (s->y < JUKU_SCAN_LINES) s->y++;
  s->rows = s->y;
  s->x = 0;
  s->line_active = 0;
}
static void video_publish(juku *j) {
  juku_scanout *s = &j->scanout;
  video_end_line(s);
  if (s->frame_started && s->width && s->rows) {
    s->frame_stride = s->width;
    s->frame_lines = s->rows;
    for (unsigned y = 0; y < s->rows; ++y)
      memcpy(s->frame + y * s->width, s->draw + y * JUKU_SCAN_STRIDE, s->width);
    s->sequence++;
    j->video_stride = s->width;
    j->video_lines = s->rows;
    /* Host prompt diagnostics only: these flags never control timing. */
    j->video_modx_mode = s->width == 50 && (s->rows == 192 || s->rows == 193);
    j->video_console_mode = j->video_modx_mode ? 3 :
      (s->width == 48 ? 2 : ((j->kbd_s21_config >> 1) & 1));
  }
  /* A complete vertically timed frame can be wholly blanked horizontally.
   * Keep the last acquired geometry, but publish black rather than retaining
   * a stale picture while software redraws video RAM (e.g. FEDITOR). */
  if (s->frame_started && !s->width && s->frame_stride && s->frame_lines) {
    memset(s->frame, 0, s->frame_stride * s->frame_lines);
    s->sequence++;
  }
  s->x = s->y = s->width = s->rows = 0;
  s->address = 0;
  s->frame_started = 1;
  memset(s->draw, 0, sizeof(s->draw));
}
void juku_video_signals(juku *j, const uint8_t previous[6]) {
  uint8_t before[6]; memcpy(before, previous, sizeof(before));
  juku_scanout *s = &j->scanout;
  /* Cascaded clocks/gates settle at the current emulated timestamp. */
  for (unsigned pass = 0; pass < 4; ++pass) {
    uint8_t now[6]; video_outputs(j, now);
    if (!memcmp(before, now, 6)) break;
    if (j->hooks.video_signal)
      for (unsigned i = 0; i < 6; ++i)
        if (before[i] != now[i]) j->hooks.video_signal(j->hooks.user, s->ns, i, now[i]);
    if (before[0] && !now[0]) pit_clock(&j->pit_counters[1][0]);
    pit_gate(&j->pit_counters[0][1], now[0]);
    pit_gate(&j->pit_counters[0][2], now[0]);
    pit_gate(&j->pit_counters[1][1], now[3]);
    pit_gate(&j->pit_counters[1][2], now[3]);
    if (!before[2] && now[2]) {
      /* A retrigger extends Q2; it does not create another falling CLK. */
      if (!s->hsync_active) {
        pit_clock(&j->pit_counters[1][1]);
        pit_clock(&j->pit_counters[1][2]);
      }
      s->hsync_active = 1;
      s->hsync_end_ns = s->ns + 5040;
    }
    /* If horizontal retriggering keeps OUT1 low for whole lines, those
     * lines still occupy vertical raster positions; they contain black. */
    if (!before[0] && now[0] && !now[1] && now[4]) {
      video_end_line(s);
      s->line_active = 1;
    }
    if (before[1] && !now[1]) video_end_line(s);
    if (before[4] && !now[4]) {
      video_publish(j);
      s->frame_event = s->irq_pending = 1; /* D35 inversion: /VER RTR -> IR5 rising edge. */
    }
    memcpy(before, now, 6);
  }
}
void juku_video_advance(juku *j) {
  juku_scanout *s = &j->scanout;
  unsigned long elapsed = j->cpu.cyc - s->last_cycle;
  s->last_cycle = j->cpu.cyc;
  /* No clocked video state exists until the first control/count write.
   * Also permits diagnostic harnesses to set an initial CPU epoch. */
  uint64_t target = s->ns + (uint64_t)elapsed * 500;
  if (!j->pit_counters[0][0].armed && !j->pit_counters[0][1].armed &&
      !j->pit_counters[0][2].armed) {
    s->ns = target;
    s->next_byte_ns = target - target % 1000 + 1000;
    return;
  }
  while (s->next_byte_ns <= target) {
    s->ns = s->next_byte_ns;
    s->next_byte_ns += 1000;
    if (s->hsync_active && s->hsync_end_ns <= s->ns) s->hsync_active = 0;
    uint8_t before[6]; video_outputs(j, before);
    /* Clock all three counters with their pre-edge gate inputs. */
    for (unsigned i = 0; i < 3; ++i) pit_clock(&j->pit_counters[0][i]);
    juku_video_signals(j, before);
    if (j->pit_counters[0][1].output && j->pit_counters[1][1].output &&
        j->pit_counters[0][1].armed && j->pit_counters[1][1].armed) {
      if (s->x < JUKU_SCAN_STRIDE && s->y < JUKU_SCAN_LINES)
        s->draw[s->y * JUKU_SCAN_STRIDE + s->x] = j->ram[(uint16_t)(VRAM_BASE + s->address)];
      if (s->x < JUKU_SCAN_STRIDE) s->x++;
      s->address = (s->address + 1) & 0xffff;
      s->line_active = 1;
    }
  }
  s->ns = target;
  if (s->hsync_active && s->hsync_end_ns <= target) s->hsync_active = 0;
}
const uint8_t *juku_frame(juku *j, unsigned *stride, unsigned *lines, uint64_t *sequence) {
  if (!j) return NULL;
  if (stride) *stride = j->scanout.frame_stride;
  if (lines) *lines = j->scanout.frame_lines;
  if (sequence) *sequence = j->scanout.sequence;
  return j->scanout.sequence ? j->scanout.frame : NULL;
}
