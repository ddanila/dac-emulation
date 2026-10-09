#include "dac.h"
#include "../../machines/juku/juku_internal.h"
#include "../../machines/robotron1715m/robotron.h"
#include "../../machines/vjuga/vjuga.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
struct dac_session {
  unsigned kind, on, width, height;
  uint8_t firmware[16384], prom[256], glyphs[4096];
  size_t firmware_size, prom_size, glyph_size, disk_size;
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
      if (!key)
        s->r->key_read = s->r->key_write;
      return 0;
    }
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
