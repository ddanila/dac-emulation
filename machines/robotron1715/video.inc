/* MIT. Ordinary PC1715 display, from ZRE schematic sheet 2 and Intel 8275.
 * Digital functional timing: fetch one byte on each CPU refresh assertion.
 * No separate W/M video RAM/DMA controller, no diagnostic-specific rendering.
 * Optional quasi-graphics jumper modification is not modelled. */
static void video_reset(pc1715_video *v) {
  /* ROM/configuration and observer survive reset. */
  memset(&v->reg, 0, sizeof(*v) - offsetof(pc1715_video, reg));
  for (unsigned i = 0; i < 640 * 288; i++)
    v->pixels[i] = 0xff000000;
}
int pc1715_video_load(pc1715 *m, const void *data, size_t n) {
  if (!m || !data || n != 4096)
    return -EINVAL;
  if (m->cpu.cycles)
    return -EBUSY;
  memcpy(m->video.glyphs, data, n);
  m->video.enabled = 1;
  return 0;
}
static unsigned vcols(pc1715_video *v) {
  unsigned n = (v->reg[0] & 127) + 1;
  return n > 80 ? 80 : n;
}
static unsigned vrows(pc1715_video *v) {
  unsigned n = (v->reg[1] & 63) + 1;
  return n > 24 ? 24 : n;
}
static unsigned vlines(pc1715_video *v) { return (v->reg[2] & 15) + 1; }
static unsigned vtotal(pc1715_video *v) {
  return vrows(v) + (v->reg[1] >> 6) + 1;
}
static void vrequest(pc1715_video *v) {
  memset(v->codes, 0xf0, 80);
  v->fetch_col = v->fifo_count = v->fifo_next = 0;
  v->fetching = !v->stop;
  v->row_valid = 0;
  v->burst = v->fetch_wait = 0;
}
int pc1715_video_read(pc1715 *m, uint16_t address, uint8_t *data) {
  pc1715_video *v = &m->video;
  unsigned a = address & 255;
  if (!v->enabled || (a & 0xfc) != 0x18)
    return 0;
  if (a & 1) {
    *data = v->status;
    v->status &= 0x44;
  } else
    *data = 0; /* no light pen connected */
  return 1;
}
int pc1715_video_write(pc1715 *m, uint16_t address, uint8_t data) {
  pc1715_video *v = &m->video;
  unsigned a = address & 255;
  if (!v->enabled)
    return 0;
  if ((a & 0xfc) == 0x34) {
    v->latch = data;
    return 1;
  }
  if ((a & 0xfc) != 0x18)
    return 0;
  if (!(a & 1)) {
    if (v->pos < v->end)
      v->reg[v->pos++] = data;
    else
      v->status |= 8;
    return 1;
  }
  unsigned incomplete = v->pos < v->end;
  v->pos = v->end = 0;
  v->preset = 0;
  switch (data >> 5) {
  case 0:
    v->running = v->clocked = v->primed = 0;
    v->status = 0;
    v->end = 4;
    v->fetching = 0;
    break;
  case 1:
    v->running = 1;
    v->status |= 0x44;
    v->dma = data & 31;
    v->primed = 0;
    if (!v->clocked) {
      v->clocked = 1;
      v->row = vtotal(v) - 1;
      v->line = v->column = v->fraction = 0;
      v->stream = v->field = v->stop = 0;
      vrequest(v);
    }
    break;
  case 2:
    v->running = v->fetching = 0;
    v->status &= ~4;
    break;
  case 4:
    v->pos = 4;
    v->end = 6;
    break;
  case 5:
    v->status |= 0x40;
    break;
  case 6:
    v->status &= ~0x40;
    break;
  case 7:
    v->preset = 1;
    v->row = v->line = v->column = v->fraction = 0;
    break;
  default:
    break;
  }
  if (incomplete)
    v->status |= 8;
  return 1;
}
static void vfetch(pc1715 *m) {
  pc1715_video *v = &m->video;
  /* A23.2 D1..D5 drive A22.4 -> AB11..AB15; X12 selects counter AB10. */
  uint16_t address = ((v->latch & 0x3e) << 10) | (v->stream++ & 2047);
  uint8_t code = m->ram[address];
  v->fetches++;
  if (v->row >= vrows(v))
    v->vsync = 0;
  if (++v->burst == (1u << (v->dma & 3))) {
    v->burst = 0;
    v->fetch_wait = (v->dma >> 2) * 8;
  }
  if (v->fifo_next) {
    if (v->fifo_count < 16)
      v->fifo[v->fifo_count++] = code & 127;
    else {
      v->status |= 1;
      v->overflows++;
    }
    v->fifo_next = 0;
  } else {
    v->codes[v->fetch_col++] = code;
    if ((code & 0xc0) == 0x80 && !(v->reg[3] & 64))
      v->fifo_next = 1;
    if (code >= 0xf0) {
      if (code == 0xf2 || code == 0xf3)
        v->stop = 1;
      /* EOR/EOS terminate this row; stop-DMA variants are used by firmware. */
      v->fetching = 0;
      v->row_valid = 1;
    }
  }
  if (v->fetch_col >= vcols(v) && !v->fifo_next) {
    v->fetching = 0;
    v->row_valid = 1;
  }
}
static void vlatch(pc1715_video *v) {
  unsigned f = 0, ended = 0;
  if (v->fetching) {
    v->status |= 2;
    v->underruns++;
  }
  for (unsigned x = 0; x < vcols(v); x++) {
    unsigned c = v->codes[x], attr = v->field, blank = ended;
    if ((c & 0xc0) == 0x80) {
      attr = v->field = c & 63;
      if (v->reg[3] & 64)
        blank = 1;
      else if (f < v->fifo_count)
        c = v->fifo[f++];
      else
        blank = 1;
    } else if (c >= 0xf0) {
      blank = ended = 1;
    } else if (c >= 0xc0) {
      /* Character attributes: H/B plus line drawing output (below). */
      attr = (attr & 0x3c) | (c & 3);
    }
    v->chars[x] = c;
    v->attrs[x] = attr;
    v->blank[x] = blank;
  }
}
static unsigned vbits(pc1715_video *v, unsigned x, unsigned y, unsigned *high) {
  unsigned c = v->chars[x], a = v->attrs[x], n = vlines(v);
  unsigned gy = (v->reg[3] & 128) ? (y + n - 1) % n : y;
  unsigned bank = ((v->latch >> 6) ^ (a >> 2)) & 1;
  unsigned bits = v->glyphs[bank * 2048 + gy * 128 + (c & 127)];
  unsigned blank = v->blank[x] || ((a & 2) && v->frames % 64 < 32);
  if (c >= 0xc0 && c < 0xf0) {
    /* Intel 8275 character attribute outputs. LA0/LA1 are unconnected on
     * the stock board, but VSP and LTEN still act on the glyph stream. */
    static const uint8_t ca[3][16] = {
        {2, 2, 4, 4, 2, 4, 4, 4, 2, 4, 4, 0, 2, 0, 0, 0},
        {8, 12, 8, 12, 1, 12, 8, 1, 1, 4, 1, 0, 2, 0, 0, 0},
        {4, 4, 2, 2, 4, 4, 4, 2, 2, 4, 4, 0, 2, 0, 0, 0}};
    unsigned underline = v->reg[2] >> 4;
    unsigned flags = ca[y < underline    ? 0
                        : y == underline ? 1
                                         : 2][(c >> 2) & 15];
    if (flags & 1)
      bits = 255;
    if (flags & 2)
      blank = 1;
  }
  if ((a & 32) && y == (v->reg[2] >> 4))
    bits = 255;
  if (a & 16)
    bits ^= 255;
  unsigned format = (v->reg[3] >> 4) & 3;
  if (x == v->reg[4] && v->row == v->reg[5] &&
      ((format & 2) || v->frames % 32 < 16)) {
    if (!(format & 1))
      bits ^= 255;
    else if (y == (v->reg[2] >> 4))
      bits = 255;
  }
  *high = (a & 1) != 0;
  return blank ? 0 : bits;
}
void pc1715_video_tick(pc1715 *m) {
  pc1715_video *v = &m->video;
  if (!v->enabled || !v->clocked || v->preset)
    return;
  unsigned refresh = (m->cpu.pins & Z80_RFSH) != 0;
  if (refresh && !v->refresh && v->fetching && !v->fetch_wait)
    vfetch(m);
  v->refresh = refresh;
  /* Independent 13.824 MHz video and nominal 2.458 MHz CPU oscillators. */
  v->fraction += 1728000;
  if (v->fraction < PC1715_CLOCK_HZ)
    return;
  v->fraction -= PC1715_CLOCK_HZ;
  if (v->fetch_wait)
    v->fetch_wait--;
  unsigned cols = vcols(v), rows = vrows(v), lines = vlines(v);
  unsigned h = v->column >= cols, vert = v->row >= rows, high = 0, bits = 0;
  if (!h && !vert && v->running && v->primed)
    bits = vbits(v, v->column, v->line, &high);
  for (unsigned bit = 0; bit < 8; bit++) {
    unsigned lit = (bits >> (7 - bit)) & 1;
    if (!h && !vert && v->line < 12)
      v->pixels[(v->row * 12 + v->line) * 640 + v->column * 8 + bit] =
          lit ? (high ? 0xffffffff : 0xffaaaaaa) : 0xff000000;
    if (v->signal) {
      unsigned hp = v->column * 8 + bit - cols * 8;
      unsigned sync = !(h && hp < 83); /* nominal 6 us monostable */
      if (v->vsync)
        sync = !sync;
      v->signal(v->user, v->dots, lit, high, sync, h, vert);
    }
    v->dots++;
  }
  if (++v->column < cols + 2 * ((v->reg[3] & 15) + 1))
    return;
  v->column = 0;
  if (++v->line < lines)
    return;
  v->line = 0;
  if (++v->row == vtotal(v)) {
    v->row = 0;
    v->frames++;
    v->field = 0;
  }
  if (v->row == rows)
    v->vsync = 1;
  if (v->row < rows) {
    if (v->row == 0)
      v->primed = v->running;
    if (v->running && v->primed)
      vlatch(v);
    if (v->row == rows - 1 && (v->status & 64))
      v->status |= 32;
    if (v->running && v->primed && v->row + 1 < rows)
      vrequest(v);
    else
      v->fetching = 0;
  } else if (v->row == vtotal(v) - 1) {
    v->stream = v->stop = 0;
    if (v->running)
      vrequest(v);
  }
}
