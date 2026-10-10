#include "dac.h"
#include "../../machines/juku/juku_internal.h"
#include "../../machines/robotron1715m/robotron.h"
#include "../../machines/vjuga/vjuga.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
struct dac_session {
  unsigned kind, on, width, height;
  uint8_t firmware[16384], prom[256], glyphs[4096], keyboard[2048];
  size_t firmware_size, prom_size, glyph_size, disk_size, keyboard_size;
  int writable;
  uint8_t *disk;
  juku *j;
  vjuga *v;
  robotron *r;
  uint32_t pixels[640 * 384];
};
dac_session *dac_create(unsigned kind) {
  if (kind > 2)
    return NULL;
  dac_session *s = calloc(1, sizeof(*s));
  if (!s)
    return NULL;
  s->kind = kind;
  s->width = kind == 2 ? 640 : 320;
  s->height = kind == 2 ? 384 : 241;
  if (kind == 0)
    s->j = juku_create();
  else if (kind == 1)
    s->v = calloc(1, sizeof(vjuga));
  else
    s->r = calloc(1, sizeof(robotron));
  if (!s->j && !s->v && !s->r) {
    free(s);
    return NULL;
  }
  return s;
}
void dac_destroy(dac_session *s) {
  if (!s)
    return;
  free(s->j);
  free(s->v);
  free(s->r);
  free(s->disk);
  free(s);
}
int dac_load(dac_session *s, unsigned slot, const void *p, size_t n) {
  if (!s || !p || s->on)
    return -EINVAL;
  if (slot == 0) {
    if (n != (s->kind == 2 ? 2048u : 16384u))
      return -EINVAL;
    memcpy(s->firmware, p, n);
    s->firmware_size = n;
  } else if (slot == 1 && s->kind == 2 && n == 256) {
    memcpy(s->prom, p, n);
    s->prom_size = n;
  } else if (slot == 2 && s->kind == 2 && (n == 2048 || n == 4096)) {
    memset(s->glyphs, 0, sizeof(s->glyphs));
    memcpy(s->glyphs, p, n);
    s->glyph_size = n;
  } else if (slot == 3 && s->kind == 2 && n == 2048) {
    memcpy(s->keyboard, p, n);
    s->keyboard_size = n;
  } else
    return -EINVAL;
  return 0;
}
int dac_mount(dac_session *s, const void *p, size_t n, int writable) {
  if (!s || s->on || !p || s->kind == 1)
    return -EINVAL;
  if (s->kind == 2 ? n != 819200
                   : (n != JUK_SINGLE_SIDED_SIZE && n != JUK_DOUBLE_SIDED_SIZE))
    return -EINVAL;
  uint8_t *copy = malloc(n);
  if (!copy)
    return -ENOMEM;
  memcpy(copy, p, n);
  free(s->disk);
  s->disk = copy;
  s->disk_size = n;
  s->writable = writable;
  return 0;
}
int dac_power(dac_session *s, int on) {
  if (!s)
    return -EINVAL;
  if (!on) {
    s->on = 0;
    if (s->j)
      juku_key(s->j, 0, 0);
    memset(s->pixels, 0, sizeof(s->pixels));
    return 0;
  }
  if (s->on)
    return 0;
  if (!s->firmware_size || (s->kind == 2 && !s->prom_size))
    return -ENOENT;
  if (s->j) {
    juku *next = juku_create();
    if (!next)
      return -ENOMEM;
    free(s->j);
    s->j = next;
    juku_load_rom(s->j, s->firmware, s->firmware_size);
    s->j->frame_cyc = s->j->next_frame = 40000;
    juku_key(s->j, 0, 0);
    if (s->disk) {
      int heads = s->disk_size == JUK_DOUBLE_SIDED_SIZE ? 2 : 1;
      juk_disk_bind(&s->j->disk,
                    dac_memory_storage(s->disk, s->disk_size, s->writable),
                    heads, s->writable);
      juku_fdc_init(&s->j->fdc, &s->j->disk);
      s->j->fdc_enabled = 1;
    }
  } else if (s->v) {
    vjuga_init(s->v, 0);
    vjuga_load_rom(s->v, s->firmware, s->firmware_size);
  } else {
    robotron_init(s->r);
    robotron_load(s->r, s->firmware, s->firmware_size, s->prom, s->prom_size);
    memcpy(s->r->chargen, s->glyphs, s->glyph_size);
    if (s->keyboard_size)
      robotron_keyboard_load(s->r, s->keyboard, s->keyboard_size);
    if (s->disk)
      robotron_disk(s->r,
                    dac_memory_storage(s->disk, s->disk_size, s->writable),
                    s->writable);
  }
  s->on = 1;
  return 0;
}
int dac_reset(dac_session *s) {
  int r = dac_power(s, 0);
  return r ? r : dac_power(s, 1);
}
unsigned dac_run(dac_session *s, unsigned ticks) {
  if (!s || !s->on)
    return 0;
  if (ticks > 100000)
    ticks = 100000;
  if (s->j) {
    unsigned long start = s->j->cpu.cyc;
    while (s->j->cpu.cyc - start < ticks) {
      if (s->j->cpu.halted)
        s->j->cpu.cyc += 4;
      else
        juku_step_cpu(s->j);
      juku_step_devices(s->j);
    }
    return (unsigned)(s->j->cpu.cyc - start);
  }
  if (s->v)
    vjuga_run(s->v, ticks);
  else
    robotron_run(s->r, ticks);
  return ticks;
}
int dac_key(dac_session *s, unsigned key, int down) {
  if (!s || !s->on || key > 255)
    return -EINVAL;
  if (s->j) {
    juku_key(s->j, (uint8_t)key, down);
    return 0;
  }
  if (s->r) {
    if (!down) {
      if (!key) {
        s->r->key_read = s->r->key_write;
        robotron_keyboard_release(&s->r->keyboard);
      }
      return 0;
    }
    if (s->r->keyboard_enabled)
      return -ENOTSUP;
    return robotron_key(s->r, (uint8_t)key);
  }
  return -ENOTSUP;
}
unsigned dac_width(dac_session *s) { return s ? s->width : 0; }
unsigned dac_height(dac_session *s) { return s ? s->height : 0; }
const uint32_t *dac_video(dac_session *s) {
  if (!s)
    return NULL;
  if (!s->on) {
    for (unsigned i = 0; i < s->width * s->height; i++)
      s->pixels[i] = 0xff000000;
    return s->pixels;
  }
  if (s->r) {
    robotron_video(s->r, s->pixels, &s->width, &s->height);
  } else {
    unsigned stride = 40, lines = 241;
    const uint8_t *p =
        s->v ? s->v->ram + 0xd800 : juku_video(s->j, &stride, &lines);
    if (stride * 8 > 640 || lines > 384)
      return NULL;
    s->width = stride * 8;
    s->height = lines;
    for (unsigned y = 0; y < lines; y++)
      for (unsigned x = 0; x < stride * 8; x++)
        s->pixels[y * stride * 8 + x] =
            (p[y * stride + (x >> 3)] & (128 >> (x & 7))) ? 0xff83e7a0
                                                          : 0xff101812;
  }
  return s->pixels;
}
const uint8_t *dac_disk_data(dac_session *s) { return s ? s->disk : NULL; }
unsigned dac_disk_size(dac_session *s) {
  return s ? (unsigned)s->disk_size : 0;
}
unsigned dac_disk_activity(dac_session *s) {
  if (!s)
    return 0;
  if (s->r)
    return (unsigned)(s->r->disk_reads + s->r->disk_writes);
  return 0;
}

int dac_matrix(dac_session *s, unsigned key, int down) {
  if (!s || !s->on || !s->r || !s->r->keyboard_enabled)
    return -EINVAL;
  return robotron_keyboard_key(&s->r->keyboard, key / 8, key % 8, down);
}
int dac_tap(dac_session *s, unsigned key, unsigned modifiers) {
  if (!s || !s->on || !s->r || !s->r->keyboard_enabled)
    return -EINVAL;
  return robotron_keyboard_tap(&s->r->keyboard, key, modifiers);
}
unsigned dac_keyboard_leds(dac_session *s) {
  return s && s->on && s->r ? s->r->keyboard.leds : 0;
}
unsigned dac_drive_status(dac_session *s) {
  if (!s || !s->on || !s->r)
    return 0;
  robotron *r = s->r;
  return (!(r->motor & 128)) | (!(r->motor & 8) << 1) |
         ((r->fdc.unit & 3) << 2) | ((r->fdc.phase == 2) << 4) |
         (r->disk.writable << 5) | ((r->fdc.cylinder[0] & 255) << 8);
}

/* Internal, same-build snapshots. The browser keys these by the WASM hash.
 * No pointers are persisted; CRC detects corruption, bounds reject bad state.
 * Restore is atomic and requires the same firmware, disk size and write mode.
 */
typedef struct {
  uint32_t magic, version, size, disk_size, writable, crc;
} state_header;
static uint32_t state_crc(const uint8_t *p, size_t n) {
  uint32_t crc = ~0u;
  while (n--) {
    crc ^= *p++;
    for (unsigned i = 0; i < 8; i++)
      crc = (crc >> 1) ^ (0xedb88320u & (0u - (crc & 1)));
  }
  return ~crc;
}
unsigned dac_state_size(dac_session *s) {
  return s && s->r && s->on ? (unsigned)(sizeof(state_header) +
                                         sizeof(robotron) + s->disk_size)
                            : 0;
}
int dac_state_save(dac_session *s, void *p, size_t n) {
  if (!p || !dac_state_size(s) || n != dac_state_size(s))
    return -EINVAL;
  robotron *copy = malloc(sizeof(*copy));
  if (!copy)
    return -ENOMEM;
  memcpy(copy, s->r, sizeof(*copy));
  memset(&copy->cpu.bus, 0, sizeof(copy->cpu.bus));
  memset(&copy->keyboard.cpu.bus, 0, sizeof(copy->keyboard.cpu.bus));
  copy->keyboard.serial = NULL;
  copy->keyboard.serial_user = NULL;
  memset(&copy->trace, 0, sizeof(copy->trace));
  memset(&copy->disk, 0, sizeof(copy->disk));
  uint8_t *payload = (uint8_t *)p + sizeof(state_header);
  memcpy(payload, copy, sizeof(*copy));
  free(copy);
  if (s->disk_size)
    memcpy(payload + sizeof(robotron), s->disk, s->disk_size);
  state_header h = {0x44414353,
                    1,
                    (uint32_t)n,
                    (uint32_t)s->disk_size,
                    (uint32_t)s->writable,
                    state_crc(payload, n - sizeof(h))};
  memcpy(p, &h, sizeof(h));
  return 0;
}
static int valid_cpu(const dac_z80 *c) {
  return c->cpu.step <= 1708 && c->cpu.hlx_idx < 3 && c->cpu.im < 3;
}
int dac_state_load(dac_session *s, const void *p, size_t n) {
  if (!s || !s->r || !p || n < sizeof(state_header) + sizeof(robotron))
    return -EINVAL;
  state_header h;
  memcpy(&h, p, sizeof(h));
  if (h.magic != 0x44414353 || h.version != 1 || h.size != n ||
      h.disk_size != s->disk_size || h.writable != (unsigned)s->writable ||
      n != sizeof(h) + sizeof(robotron) + s->disk_size)
    return -EINVAL;
  const uint8_t *payload = (const uint8_t *)p + sizeof(h);
  if (state_crc(payload, n - sizeof(h)) != h.crc)
    return -EINVAL;
  robotron *r = malloc(sizeof(*r));
  if (!r)
    return -ENOMEM;
  memcpy(r, payload, sizeof(*r));
  robotron_fdc *f = &r->fdc;
  robotron_keyboard *k = &r->keyboard;
  int invalid =
      memcmp(r->rom, s->firmware, 2048) || memcmp(r->prom, s->prom, 256) ||
      r->keyboard_enabled != !!s->keyboard_size ||
      (s->keyboard_size && memcmp(k->rom, s->keyboard, 2048)) ||
      !valid_cpu(&r->cpu) || !valid_cpu(&k->cpu) || f->unit >= 4 ||
      f->phase > 2 || f->cmd_len > 9 || f->cmd_pos >= 9 || f->result_len > 7 ||
      f->result_pos > f->result_len ||
      (f->phase == 1 && f->result_pos >= f->result_len) ||
      f->data_len > sizeof(f->data) || f->data_pos > f->data_len ||
      (f->phase == 2 && f->data_pos >= f->data_len) || r->dma.tag_count > 10 ||
      r->dma.tag_pos > r->dma.tag_count ||
      (r->dma.tag_count && r->dma.tag_pos >= r->dma.tag_count) ||
      r->dma.read_pos >= 7 || r->sio_pointer[0] > 7 || r->sio_pointer[1] > 7 ||
      r->rx.read >= 3 || r->rx.count > 3 || r->rx.phase > 4 || r->rx.bits > 8 ||
      k->tap_read >= 64 || k->tap_count > 64 || k->tap_phase > 2 ||
      k->clock_fraction >= 3993600 || r->key_write - r->key_read > 256;
  for (unsigned i = 0; i < 64; i++)
    invalid |= k->taps[i] >= 104 || k->tap_mods[i] > 3;
  if (invalid) {
    free(r);
    return -EINVAL;
  }
  /* Repair all host callbacks from code, never from serialized addresses. */
  robotron_rebind(r);
  if (s->disk_size) {
    memcpy(s->disk, payload + sizeof(*r), s->disk_size);
    robotron_disk(r, dac_memory_storage(s->disk, s->disk_size, s->writable),
                  s->writable);
  } else
    memset(&r->disk, 0, sizeof(r->disk));
  free(s->r);
  s->r = r;
  s->on = 1;
  return 0;
}
