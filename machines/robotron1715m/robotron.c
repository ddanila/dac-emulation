/* Functional model informed by the BSD-3-Clause MAME rt1715 driver and
 * Maxim Usov's MIT Robotron FPGA development models. See NOTICE/provenance.
 * No guest addresses are patched and no guest instructions are intercepted. */
#include "robotron.h"
#include <errno.h>
#include <string.h>
static int bank(robotron *m, unsigned b, uint16_t a) {
  if (!b)
    return a < 0x4000 ? 4 + (a >> 12) : 0;
  unsigned bits = m->prom[128 + (b << 4) + (a >> 12)] ^ 15;
  switch (bits) {
  case 1:
    return 0;
  case 2:
    return 1;
  case 4:
    return 2;
  case 8:
    return 3;
  default:
    return 5;
  }
}
uint8_t robotron_read(void *p, uint16_t a) {
  robotron *m = p;
  int b = bank(m, m->bank & 7, a);
  if (b < 4)
    return m->ram[b * 65536 + a];
  if (b == 4)
    return m->rom[a & 2047];
  if (b == 6)
    return m->chargen[a & 4095];
  if (b == 7)
    return m->vram[a & 4095];
  return 0;
}
void robotron_write(void *p, uint16_t a, uint8_t v) {
  robotron *m = p;
  int b = bank(m, (m->bank >> 4) & 7, a);
  if (b < 4)
    m->ram[b * 65536 + a] = v;
  else if (b == 6)
    m->chargen[a & 4095] = v;
  else if (b == 7) {
    m->vram[a & 4095] = v;
    m->video_writes++;
  }
}
static void result(robotron *m, unsigned len) {
  m->fdc.phase = 1;
  m->fdc.result_pos = 0;
  m->fdc.result_len = len;
}
static void finish(robotron *m, uint8_t st1) {
  robotron_fdc *f = &m->fdc;
  uint8_t r[] = {(uint8_t)((f->unit | (f->head << 2)) | (st1 ? 0x40 : 0)),
                 st1,
                 0,
                 (uint8_t)f->cylinder[f->unit],
                 (uint8_t)f->head,
                 (uint8_t)f->sector,
                 (uint8_t)f->n};
  if (f->scan_mode)
    r[2] = (f->scan_mode == 17 ? f->scan_compare == 0
                               : (f->scan_mode == 25 ? f->scan_compare <= 0
                                                     : f->scan_compare >= 0))
               ? 8
               : 4;
  memcpy(f->result, r, 7);
  result(m, 7);
}
static void sector(robotron *m) {
  robotron_fdc *f = &m->fdc;
  f->data_pos = 0;
  if (f->unit || f->n != 3 || !m->disk.storage.read) {
    finish(m, 4);
    return;
  }
  f->data_len = 1024;
  f->scan_compare = 0;
  if (f->write != 1) {
    if (dac_media_read(&m->disk, f->cylinder[0], f->head, f->sector, f->data)) {
      finish(m, 4);
      return;
    }
    m->disk_reads++;
  } else if (!m->disk.writable) {
    finish(m, 2);
    return;
  }
  f->phase = 2;
  /* Ideal 300 RPM rotation, five evenly spaced IDs. Data rate 250 kbit/s.
   * No flux-level encoding, head-load time or drive spin-up model yet. */
  const unsigned revolution = 798720, slot = revolution / 5;
  unsigned phase = (unsigned)(m->cpu.cycles % revolution);
  unsigned target = ((f->sector - 1) % 5) * slot;
  f->ready_at =
      m->cpu.cycles + (target + revolution - phase) % revolution + 4000;
}
static void transfer_done(robotron *m) {
  robotron_fdc *f = &m->fdc;
  if (f->write == 1) {
    if (dac_media_write(&m->disk, f->cylinder[0], f->head, f->sector,
                        f->data)) {
      finish(m, 2);
      return;
    }
    m->disk_writes++;
  }
  if (f->scan_mode &&
      (f->scan_mode == 17 ? f->scan_compare == 0
                          : (f->scan_mode == 25 ? f->scan_compare <= 0
                                                : f->scan_compare >= 0))) {
    finish(m, 0);
    return;
  }
  if (f->tc) {
    if (f->sector < f->eot)
      f->sector++;
    else {
      f->sector = 1;
      finish(m, 0);
      f->result[3]++; /* next CHRN is not a physical seek */
      return;
    }
    finish(m, 0);
  } else if (f->sector < f->eot) {
    f->sector++;
    sector(m);
  } else {
    finish(m, 0x80); /* EOT without terminal count. */
  }
}
static unsigned command_length(uint8_t c) {
  switch (c & 31) {
  case 3:
    return 3;
  case 4:
  case 7:
  case 10:
    return 2;
  case 15:
    return 3;
  case 5:
  case 6:
  case 17:
  case 25:
  case 29:
    return 9;
  default:
    return 1;
  }
}
static void command(robotron *m, uint8_t v) {
  robotron_fdc *f = &m->fdc;
  if (f->phase || f->reset)
    return;
  if (!f->cmd_pos)
    f->cmd_len = command_length(v);
  f->command[f->cmd_pos++] = v;
  if (f->cmd_pos < f->cmd_len)
    return;
  f->cmd_pos = 0;
  uint8_t *c = f->command;
  unsigned op = c[0] & 31;
  f->tc = 0;
  f->scan_mode = 0;
  if (op == 3) {
    f->step_ticks = (16 - (c[1] >> 4)) * 3994;
    return;
  }
  if (op == 8) {
    unsigned u = 0;
    while (u < 4 && !(f->seek_done & (1u << u)))
      u++;
    f->result[0] = u < 4 ? (uint8_t)(0x20 | u) : 0x80;
    if (u < 4) {
      f->result[1] = (uint8_t)f->cylinder[u];
      f->seek_done &= ~(1u << u);
    }
    result(m, u < 4 ? 2 : 1);
    f->pending = !!f->seek_done;
    return;
  }
  f->unit = c[1] & 3;
  f->head = (c[1] >> 2) & 1;
  if (op == 4) {
    f->result[0] = (c[1] & 7) | 8 |
                   (!f->unit && m->disk.storage.read ? 32 : 0) |
                   (f->cylinder[f->unit] ? 0 : 16) |
                   (!f->unit && m->disk.writable ? 0 : 64);
    result(m, 1);
  } else if (op == 7 || op == 15) {
    unsigned target = op == 7 ? 0 : c[2];
    unsigned here = f->cylinder[f->unit];
    unsigned steps = target > here ? target - here : here - target;
    f->seek_target[f->unit] = target;
    f->seek_at[f->unit] =
        m->cpu.cycles +
        (steps ? steps : 1) * (f->step_ticks ? f->step_ticks : 23962);
    f->seeking |= 1u << f->unit;
  } else if (op == 10) {
    f->sector = f->sector % 5 + 1;
    f->n = 3;
    finish(m, !f->unit && m->disk.storage.read ? 0 : 4);
  } else if (op == 5 || op == 6 || op == 17 || op == 25 || op == 29) {
    if (f->unit || f->cylinder[f->unit] != c[2]) {
      f->sector = c[4];
      f->n = c[5];
      finish(m, 4);
      return;
    }
    f->head = c[3] & 1;
    f->sector = c[4];
    f->n = c[5];
    f->eot = c[6];
    f->scan_mode = op >= 17 ? op : 0;
    f->write = op >= 17 ? 2 : (op == 5);
    sector(m);
  } else {
    f->result[0] = 0x80;
    result(m, 1);
  }
}
static int ready(robotron *m) {
  return !m->fdc.reset && m->fdc.phase == 2 && m->cpu.cycles >= m->fdc.ready_at;
}
static uint8_t fdc_read(robotron *m) {
  robotron_fdc *f = &m->fdc;
  if (f->phase == 1) {
    uint8_t v = f->result[f->result_pos++];
    if (f->result_pos == f->result_len)
      f->phase = 0;
    return v;
  }
  if (ready(m) && !f->write) {
    uint8_t v = f->data[f->data_pos++];
    f->ready_at = m->cpu.cycles + 128;
    if (f->data_pos == f->data_len)
      transfer_done(m);
    return v;
  }
  return 0xff;
}
static void fdc_write(robotron *m, uint8_t v) {
  if (ready(m) && m->fdc.write) {
    robotron_fdc *f = &m->fdc;
    if (f->scan_mode) {
      if (!f->scan_compare)
        f->scan_compare = (int)f->data[f->data_pos] - (int)v;
    } else
      f->data[f->data_pos] = v;
    f->data_pos++;
    f->ready_at = m->cpu.cycles + 128;
    if (f->data_pos == f->data_len)
      transfer_done(m);
  } else
    command(m, v);
}
static void dma_parameter(robotron_dma *d, uint8_t v) {
  unsigned tag = d->tags[d->tag_pos++];
  switch (tag) {
  case 1:
    d->a = (d->a & 0xff00) | v;
    break;
  case 2:
    d->a = (d->a & 255) | (v << 8);
    break;
  case 3:
    d->count = (d->count & 0xff00) | v;
    break;
  case 4:
    d->count = (d->count & 255) | (v << 8);
    break;
  case 5:
    d->b = (d->b & 0xff00) | v;
    break;
  case 6:
    d->b = (d->b & 255) | (v << 8);
    break;
  case 7:
    d->irq_control = v;
    if (v & 8)
      d->tags[d->tag_count++] = 9;
    if (v & 16)
      d->tags[d->tag_count++] = 8;
    break;
  case 8:
    d->vector = v;
    break;
  default:
    break;
  }
  if (d->tag_pos == d->tag_count)
    d->tag_pos = d->tag_count = 0;
}
static void dma_write(robotron *m, uint8_t v) {
  robotron_dma *d = &m->dma;
  if (d->tag_count) {
    dma_parameter(d, v);
    return;
  }
  if (d->mask_pending) {
    d->mask = v;
    d->mask_pending = 0;
    d->read_pos = 0;
    return;
  }
  if (v != 0xa7)
    d->mask = 0;
  switch (v) {
  case 0xc3:
    memset(d, 0, sizeof(*d));
    d->status = 0x38;
    d->vector = 0x14;
    return;
  case 0xbb:
    d->mask_pending = 1;
    return;
  case 0x8b:
    d->status |= 0x30;
    d->irq = 0;
    return;
  case 0xab:
    d->irq_enabled = 1;
    return;
  case 0xaf:
    d->irq_enabled = 0;
    return;
  case 0xbf:
    d->mask = 1;
    d->read_pos = 0;
    return;
  case 0xa7:
    d->read_pos = 0;
    return;
  case 0xa3:
    d->irq = d->irq_enabled = d->force_ready = d->in_service = 0;
    d->status |= 8;
    return;
  case 0xb3:
    d->force_ready = 1;
    return;
  case 0x83:
    d->enabled = 0;
    return;
  case 0x87:
    d->enabled = 1;
    return;
  case 0xcf:
    d->run_a = d->a;
    d->run_b = d->b;
    d->force_ready = 0; /* fall through */
  case 0xd3:
    d->remaining = (unsigned)d->count + 1;
    d->transferred = 0;
    d->status |= 0x30;
    return;
  default:
    break;
  }
  if ((v & 0x87) == 0) {
    d->b_mode = (v >> 4) & 3;
    d->b_io = (v >> 3) & 1;
    if (v & 0x40)
      d->tags[d->tag_count++] = 9;
  } else if ((v & 0x87) == 4) {
    d->a_mode = (v >> 4) & 3;
    d->a_io = (v >> 3) & 1;
    if (v & 0x40)
      d->tags[d->tag_count++] = 9;
  } else if (!(v & 128)) {
    d->direction = (v >> 2) & 1;
    for (unsigned i = 0; i < 4; i++)
      if (v & (8 << i))
        d->tags[d->tag_count++] = i + 1;
  } else if ((v & 0xc7) == 0x82) {
    d->ready_high = (v >> 3) & 1;
  } else if ((v & 0x83) == 0x81) {
    for (unsigned i = 0; i < 3; i++)
      if (v & (4 << i))
        d->tags[d->tag_count++] = 5 + i;
  } else if ((v & 0x83) == 0x80) {
    d->irq_enabled = (v >> 5) & 1;
    if (v & 64)
      d->enabled = 1;
    for (unsigned i = 3; i <= 4; i++)
      if (v & (1 << i))
        d->tags[d->tag_count++] = 9;
  }
}
static int dma_ready(robotron *m) {
  /* PC-1715W inverts FDC DRQ before the Z80 DMA RDY input. */
  return m->dma.force_ready || ((!ready(m)) == m->dma.ready_high);
}
static uint8_t dma_read(robotron *m) {
  robotron_dma *d = &m->dma;
  uint8_t s = (d->status & 0xfd) | (dma_ready(m) ? 0 : 2);
  if (!d->mask)
    return s;
  uint8_t values[] = {s,
                      d->transferred & 255,
                      d->transferred >> 8,
                      d->run_a & 255,
                      d->run_a >> 8,
                      d->run_b & 255,
                      d->run_b >> 8};
  for (unsigned i = 0; i < 7; i++) {
    unsigned pos = d->read_pos;
    d->read_pos = (pos + 1) % 7;
    if (d->mask & (1 << pos))
      return values[pos];
  }
  return s;
}
static void ctc_write(robotron *m, unsigned n, uint8_t v) {
  robotron_timer *t = &m->ctc[n];
  if (t->waiting) {
    t->constant = v;
    t->counter = v ? v : 256;
    t->waiting = 0;
    t->prescaler = 0;
    t->control &= ~2;
    return;
  }
  if (!(v & 1)) {
    m->ctc_vector[n / 4] = v & 0xf8;
    return;
  }
  t->control = v;
  t->waiting = (v >> 2) & 1;
  if (v & 2)
    t->pending = t->in_service = 0;
}
static uint8_t input_value(void *p, uint16_t a) {
  robotron *m = p;
  a &= 255;
  if (a == 0)
    return dma_read(m);
  if (a >= 4 && a <= 11)
    return (uint8_t)m->ctc[a - 4].counter;
  if (a == 0x1c || a == 0x40)
    return m->fdc.seeking |
           (m->fdc.reset ? 0 : (m->fdc.phase == 2 && !ready(m) ? 0 : 0x80)) |
           (m->fdc.phase || m->fdc.cmd_pos ? 16 : 0) |
           ((m->fdc.phase == 1 || (ready(m) && !m->fdc.write)) ? 64 : 0);
  if (a == 0x1d || a == 0x41)
    return fdc_read(m);
  if (a >= 0x34 && a <= 0x37)
    return 1;
  if (m->keyboard_enabled && (a == 0x0c || a == 0x0e))
    return robotron_sio_read(m, a == 0x0e);
  if (a == 0x0e) {
    unsigned reg = m->sio_pointer[0];
    m->sio_pointer[0] = 0;
    return reg == 1 ? 0 : (0x7c | (m->key_read != m->key_write));
  }
  if (a == 0x0c) {
    if (m->key_read == m->key_write)
      return 0;
    return m->keys[m->key_read++ & 255];
  }
  if (a == 0x19)
    return m->crtc_status;
  if (a == 0x0f || a == 0x14 || a == 0x15)
    return 0x64;
  if (a == 0x0d || a == 0x16 || a == 0x17 || a == 0x18 || a == 0x19)
    return 0;
  return 0xff;
}
uint8_t robotron_input(void *p, uint16_t a) {
  robotron *m = p;
  uint8_t v = input_value(p, a);
  dac_trace_emit(&m->trace, "IR", a, v, m->cpu.cycles, 2);
  return v;
}
void robotron_output(void *p, uint16_t a, uint8_t v) {
  robotron *m = p;
  dac_trace_emit(&m->trace, "IW", a, v, m->cpu.cycles, 2);
  a &= 255;
  if (a == 0)
    dma_write(m, v);
  else if (a == 0x0e || a == 0x0f) {
    robotron_sio_control(m, a & 1, v);
  } else if (a >= 4 && a <= 11)
    ctc_write(m, a - 4, v);
  else if (a == 0x1d || a == 0x41)
    fdc_write(m, v);
  else if (a >= 0x24 && a <= 0x27)
    m->bank = v;
  else if (a >= 0x20 && a <= 0x23) {
    if ((m->krfd ^ v) & 64) {
      unsigned cylinders[4];
      memcpy(cylinders, m->fdc.cylinder, sizeof(cylinders));
      memset(&m->fdc, 0, sizeof(m->fdc));
      memcpy(m->fdc.cylinder, cylinders, sizeof(cylinders));
      m->fdc.reset = !(v & 64);
    }
    m->krfd = v;
  } else if (a >= 0x28 && a <= 0x2b)
    m->motor = v;
  else if (a == 0x19) {
    m->crtc_pos = m->crtc_end = 0;
    switch (v >> 5) {
    case 0:
      m->display_on = m->crtc_status = 0;
      m->crtc_end = 4;
      break;
    case 1:
      m->display_on = 1;
      m->crtc_status |= 0x44;
      break;
    case 2:
      m->display_on = 0;
      m->crtc_status &= ~4;
      break;
    case 4:
      m->crtc_pos = 4;
      m->crtc_end = 6;
      break;
    case 5:
      m->crtc_status |= 0x40;
      break;
    case 6:
      m->crtc_status &= ~0x40;
      break;
    default:
      break;
    }
  } else if (a == 0x18 && m->crtc_pos < m->crtc_end) {
    unsigned pos = m->crtc_pos++;
    if (pos < 4)
      m->crtc[pos] = v;
    else
      m->cursor[pos - 4] = v;
  }
}
/* Daisy chain: DMA, then CTC2 channels 0..3. CTC0 is not wired to INT. */
static int interrupt_source(robotron *m) {
  if (m->dma.in_service)
    return -1;
  if (m->dma.irq)
    return 0;
  for (unsigned i = 0; i < 4; i++) {
    if (m->ctc[i].in_service)
      return -1;
    if (m->ctc[i].pending)
      return (int)i + 1;
  }
  if (m->rx.pending && !m->rx.in_service)
    return 5;
  return -1;
}
static uint8_t ack(void *p) {
  robotron *m = p;
  int source = interrupt_source(m);
  if (source == 0) {
    m->dma.irq = 0;
    m->dma.in_service = 1;
    return m->dma.irq_vector;
  }
  if (source == 5) {
    m->rx.pending = 0;
    m->rx.in_service = 1;
    return (m->sio_regs[1][1] & 4) ? (m->sio_regs[1][2] & 0xf1) | 12
                                   : m->sio_regs[1][2];
  }
  if (source > 0) {
    m->ctc[source - 1].pending = 0;
    m->ctc[source - 1].in_service = 1;
    return m->ctc_vector[0] + 2 * (source - 1);
  }
  return 0xff;
}
static void reti(robotron *m) {
  if (m->dma.in_service) {
    m->dma.in_service = 0;
    return;
  }
  for (unsigned i = 0; i < 4; i++)
    if (m->ctc[i].in_service) {
      m->ctc[i].in_service = 0;
      return;
    }
  m->rx.in_service = 0;
}

void robotron_init(robotron *m) {
  memset(m, 0, sizeof(*m));
  memset(m->prom, 15, 256);
  m->dma.vector = 0x14;
  m->krfd = 0x40;
  m->crtc[0] = 79;
  m->crtc[1] = 23;
  m->crtc[2] = 0x6f;
  m->crtc[3] = 0x60;
  m->cursor[0] = m->cursor[1] = 255;
  dac_z80_init(&m->cpu, (dac_z80_bus){m, robotron_read, robotron_write,
                                      robotron_input, robotron_output, ack});
}
int robotron_load(robotron *m, const void *r, size_t nr, const void *p,
                  size_t np) {
  if (!m || !r || !p || nr != 2048 || np != 256)
    return -EINVAL;
  if (m->cpu.cycles)
    return -EBUSY;
  memcpy(m->rom, r, nr);
  memcpy(m->prom, p, np);
  return 0;
}
int robotron_disk(robotron *m, dac_storage s, int writable) {
  return dac_media_init(&m->disk, s, (dac_geometry){80, 2, 5, 1024, 1},
                        writable);
}
int robotron_key(robotron *m, uint8_t key) {
  if (m->key_write - m->key_read > 254)
    return -ENOSPC;
  m->keys[m->key_write++ & 255] = 0xe0;
  m->keys[m->key_write++ & 255] =
      (key == 13 || key == 10) ? 0x9e : (key == 27 ? 0x9b : key);
  return 0;
}
static void advance(uint16_t *a, unsigned mode) {
  if (mode == 0)
    (*a)--;
  else if (mode == 1)
    (*a)++;
}
int robotron_keyboard_load(robotron *m, const void *rom, size_t n) {
  if (!rom || n != 2048 || m->cpu.cycles)
    return -EINVAL;
  robotron_keyboard_init(&m->keyboard, rom, m, robotron_serial_clock);
  m->keyboard_enabled = 1;
  m->rx.first = 1;
  return 0;
}
void robotron_run(robotron *m, unsigned ticks) {
  while (ticks--) {
    if (m->keyboard_enabled)
      robotron_keyboard_tick(&m->keyboard);
    for (unsigned u = 0; u < 4; u++)
      if ((m->fdc.seeking & (1u << u)) && m->cpu.cycles >= m->fdc.seek_at[u]) {
        m->fdc.cylinder[u] = m->fdc.seek_target[u];
        m->fdc.seeking &= ~(1u << u);
        m->fdc.seek_done |= 1u << u;
        m->fdc.pending = 1;
      }
    unsigned cascade = 0;
    for (unsigned i = 0; i < 8; i++) {
      robotron_timer *t = &m->ctc[i];
      if (!(t->control & 2) && !t->waiting && t->counter) {
        unsigned clock = 0;
        if (t->control & 0x40)
          clock = (i == 2 && cascade);
        else if (++t->prescaler >= ((t->control & 0x20) ? 256u : 16u)) {
          t->prescaler = 0;
          clock = 1;
        }
        if (clock && !--t->counter) {
          t->counter = t->constant ? t->constant : 256;
          t->pending = (t->control >> 7) & 1;
          if (i == 1)
            cascade = 1;
        }
      }
    }
    robotron_dma *d = &m->dma;
    if (d->enabled && d->remaining && dma_ready(m)) {
      uint16_t src = d->direction ? d->run_a : d->run_b,
               dst = d->direction ? d->run_b : d->run_a;
      unsigned si = d->direction ? d->a_io : d->b_io,
               di = d->direction ? d->b_io : d->a_io;
      /* Board TC is DMA INT gated by KRFD. Set before the last byte. */
      int terminal = d->remaining == 1 && d->irq_enabled &&
                     (d->irq_control & 2) && !d->in_service && (m->krfd & 128);
      if (terminal && m->fdc.phase == 2)
        m->fdc.tc = 1;
      uint8_t v = si ? robotron_input(m, src) : robotron_read(m, src);
      if (di)
        robotron_output(m, dst, v);
      else
        robotron_write(m, dst, v);
      advance(&d->run_a, d->a_mode);
      advance(&d->run_b, d->b_mode);
      d->transferred++;
      if (!--d->remaining) {
        if (terminal && m->fdc.phase == 2) {
          /* Short writes finish the physical sector with zero padding. */
          if (m->fdc.write == 1) {
            memset(m->fdc.data + m->fdc.data_pos, 0,
                   m->fdc.data_len - m->fdc.data_pos);
            transfer_done(m);
          } else
            transfer_done(m);
        }
        d->enabled = 0;
        d->status = 0x19;
        if (d->irq_enabled && (d->irq_control & 2) && !d->in_service) {
          d->irq = 1;
          d->irq_vector =
              (d->irq_control & 32) ? (d->vector & 0xf9) | 4 : d->vector;
          d->status &= ~8;
        }
      }
      /* CPU bus ownership is paused while DMA transfers. */
      m->cpu.cycles++;
    } else {
      dac_z80_tick(&m->cpu, interrupt_source(m) >= 0, 0);
      if (m->cpu.pins & Z80_RETI)
        reti(m);
    }
  }
}

/* Bounded 8275 character-stream renderer, without raster/DMA scheduling.
 * Field attributes carry between rows. Non-display attributes consume the
 * following stream byte. The physical video address wraps at 80*24. */
void robotron_video(robotron *m, uint32_t *pixels, unsigned *width,
                    unsigned *height) {
  unsigned cols = (m->crtc[0] & 127) + 1, rows = (m->crtc[1] & 63) + 1;
  unsigned lines = (m->crtc[2] & 15) + 1, underline = m->crtc[2] >> 4;
  if (cols > 80)
    cols = 80;
  if (rows > 24)
    rows = 24;
  *width = cols * 8;
  *height = rows * lines;
  unsigned pos = 0, field = 0, end_screen = 0;
  unsigned frame = (unsigned)(m->cpu.cycles / 80000); /* 4 MHz, nominal 50 Hz */
  for (unsigned row = 0; row < rows; row++) {
    unsigned end_row = 0;
    for (unsigned col = 0; col < cols; col++) {
      uint8_t ch = m->vram[pos++ % 1920];
      unsigned attr = field, blank = end_row || end_screen || !m->display_on;
      if ((ch & 0xc0) == 0x80) {
        field = ch & 63;
        if (m->crtc[3] & 64)
          blank = 1;
        else {
          ch = m->vram[pos++ % 1920];
          attr = field;
        }
      }
      if (ch >= 0xf0) {
        blank = 1;
        if (ch == 0xf0 || ch == 0xf1)
          end_row = 1;
        if (ch == 0xf2 || ch == 0xf3)
          end_screen = 1;
      } else if (ch >= 0xc0) {
        /* Line-drawing attribute characters require a separate decoder. */
        blank = 1;
      }
      for (unsigned y = 0; y < lines; y++) {
        unsigned gy = (m->crtc[3] & 128) ? (y + lines - 1) % lines : y;
        uint8_t bits =
            m->chargen[((attr & 4) ? 2048 : 0) + gy * 128 + (ch & 127)];
        if ((attr & 2) && (frame % 64 < 32))
          bits = 0;
        if ((attr & 32) && y == underline)
          bits = 255;
        if (attr & 16)
          bits ^= 255;
        unsigned format = (m->crtc[3] >> 4) & 3;
        if (row == m->cursor[1] && col == m->cursor[0] &&
            ((format & 2) || frame % 32 < 16)) {
          if (format & 1) {
            if (y == underline)
              bits = 255;
          } else
            bits ^= 255;
        }
        if (blank)
          bits = 0;
        for (unsigned x = 0; x < 8; x++)
          pixels[(row * lines + y) * *width + col * 8 + x] =
              (bits & (128 >> x)) ? ((attr & 1) ? 0xffb0ffcb : 0xff83e7a0)
                                  : 0xff101812;
      }
    }
  }
}

void robotron_rebind(robotron *m) {
  m->cpu.bus = (dac_z80_bus){
      m, robotron_read, robotron_write, robotron_input, robotron_output, ack};
  robotron_keyboard_rebind(&m->keyboard, m, robotron_serial_clock);
  memset(&m->trace, 0, sizeof(m->trace));
}
