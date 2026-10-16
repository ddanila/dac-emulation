#include "session.h"
#include "../../machines/juku/juku_internal.h"
#include "../../machines/robotron1715m/robotron.h"
#include "../../machines/vjuga/vjuga.h"
#include "observe.h"
#define CHIPS_UTIL_IMPL
#include "../../third_party/cpu/chips/z80dasm.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
struct dac_session {
  unsigned kind, on, width, height;
  dac_trace_sink observer;
  unsigned timeline_on, timeline_count, timeline_mode, timeline_pre,
      timeline_triggered, timeline_index, timeline_filter, timeline_master,
      timeline_address;
  uint32_t timeline[512][13];
  unsigned debug_break, debug_hit, debug_exec, debug_address;
  char debug_text[128];
  uint8_t firmware[16384], prom[256], glyphs[4096], keyboard[2048];
  size_t firmware_size, prom_size, glyph_size, disk_size, keyboard_size;
  int writable, writable_b;
  size_t disk_b_size;
  uint8_t *disk_b;
  uint8_t *disk;
  juku *j;
  vjuga *v;
  robotron *r;
  uint32_t pixels[640 * 384];
};
#ifndef DAC_BUILD_ID
#define DAC_BUILD_ID "unversioned"
#endif
const char *dac_runtime_build_id(void) { return DAC_BUILD_ID; }
unsigned dac_verification_abi(void) { return 1; }
static void bind_observer(dac_session *s);
static void forward_trace(void *user, const dac_trace_event *event) {
  dac_session *s = user;
  dac_trace_emit_event(&s->observer, event);
  unsigned kind = event->kind[0] == 'M'   ? (event->kind[1] == 'R' ? 0 : 1)
                  : event->kind[1] == 'R' ? 2
                  : event->kind[1] == 'W' ? 3
                                          : 4;
  int match = s->timeline_mode == 0 ||
              (s->timeline_mode == 1 && kind == 3 &&
               (event->address & 255) == s->timeline_address) ||
              (s->timeline_mode == 2 && kind == 2 &&
               (event->address & 255) == s->timeline_address) ||
              (s->timeline_mode == 3 && kind == 1 &&
               event->address == s->timeline_address) ||
              (s->timeline_mode == 4 && event->master == DAC_MASTER_DMA) ||
              (s->timeline_mode == 5 && kind == 4);
  int selected =
      (!s->timeline_master || event->master == s->timeline_master - 1) &&
      ((s->timeline_filter & (1u << kind)) ||
       (s->timeline_filter == 28 && event->master == DAC_MASTER_DMA));
  if (s->timeline_on && s->r && s->timeline_count < 512 &&
      (selected || (!s->timeline_triggered && match))) {
    if (!s->timeline_triggered && match) {
      s->timeline_triggered = 1;
      if (s->debug_break)
        s->debug_hit = 1;
      s->timeline_index = s->timeline_count + 1;
    }
    if (!s->timeline_triggered) {
      if (!s->timeline_pre)
        return;
      if (s->timeline_count == s->timeline_pre) {
        memmove(s->timeline, s->timeline + 1,
                (s->timeline_count - 1) * sizeof(s->timeline[0]));
        s->timeline_count--;
      }
    }
    if (s->debug_break && s->timeline_mode == 0)
      s->debug_hit = 1;
    uint32_t *row = s->timeline[s->timeline_count++];
    row[0] = (uint32_t)event->cycle;
    row[1] = (uint32_t)(event->cycle >> 32);
    row[2] = event->kind[0] == 'M'   ? (event->kind[1] == 'R' ? 0 : 1)
             : event->kind[1] == 'R' ? 2
             : event->kind[1] == 'W' ? 3
                                     : 4;
    row[3] = event->address;
    row[4] = event->data;
    row[5] = event->master;
    row[6] = event->space;
    row[7] = event->offset;
    row[8] = s->r->fdc.unit;
    row[9] = s->r->fdc.cylinder[s->r->fdc.unit & 3];
    row[10] = s->r->fdc.head;
    row[11] = s->r->fdc.sector;
    row[12] = s->r->fdc.phase;
    if (s->timeline_count == 512) {
      s->timeline_on = 0;
      bind_observer(s);
    }
  }
}
static void bind_observer(dac_session *s) {
  dac_trace_sink sink = {
      (s->observer.emit || s->timeline_on) ? forward_trace : NULL, s, 0, 0};
  if (s->j)
    s->j->bus_trace = sink;
  if (s->r)
    s->r->trace = sink;
}
void dac_timeline_capture(dac_session *s, unsigned enabled) {
  if (!s)
    return;
  s->timeline_count = 0;
  s->timeline_mode = 0;
  s->timeline_pre = 0;
  s->timeline_triggered = 1;
  s->timeline_index = 0;
  s->timeline_filter = 28;
  s->timeline_master = 0;
  s->timeline_on = !!enabled;
  bind_observer(s);
}
int dac_timeline_arm(dac_session *s, unsigned mode, unsigned address,
                     unsigned pre, unsigned filter, unsigned master) {
  if (!s || !s->r || mode > 5 || address > 65535 || pre > 128 || !filter ||
      filter > 31 || master > 2)
    return -EINVAL;
  dac_timeline_capture(s, 0);
  s->timeline_mode = mode;
  s->timeline_address = address;
  s->timeline_pre = pre;
  s->timeline_filter = filter;
  s->timeline_master = master;
  s->timeline_triggered = mode == 0;
  s->timeline_on = 1;
  bind_observer(s);
  return 0;
}
void dac_timeline_stop(dac_session *s) {
  if (s) {
    s->timeline_on = 0;
    bind_observer(s);
  }
}
unsigned dac_timeline_status(dac_session *s) {
  return !s               ? 0
         : s->timeline_on ? (s->timeline_triggered ? 2 : 1)
                          : (s->timeline_count ? 3 : 0);
}
unsigned dac_timeline_trigger(dac_session *s) {
  return s ? s->timeline_index : 0;
}
unsigned dac_timeline_count(dac_session *s) {
  return s ? s->timeline_count : 0;
}
const uint32_t *dac_timeline_data(dac_session *s) {
  return s ? &s->timeline[0][0] : NULL;
}
int dac_set_trace(dac_session *s, const dac_trace_sink *sink) {
  if (!s)
    return -EINVAL;
  if (s->v && sink)
    return -ENOTSUP;
  s->observer = sink ? *sink : (dac_trace_sink){0};
  bind_observer(s);
  return 0;
}
int dac_observe(dac_session *s, dac_observation *out) {
  if (!s || !s->on || !out)
    return -EINVAL;
  if (s->j) {
    *out = (dac_observation){s->j->cpu.cyc, s->j->cpu.pc, s->j->cpu.sp,
                             s->j->cpu.halted, (unsigned)s->j->mode};
  } else {
    dac_z80 *cpu = s->r ? &s->r->cpu : &s->v->cpu;
    *out = (dac_observation){cpu->cycles, cpu->cpu.pc, cpu->cpu.sp,
                             !!(cpu->pins & Z80_HALT),
                             s->r ? s->r->bank : s->v->portc};
  }
  return 0;
}
int dac_peek(dac_session *s, unsigned space, uint32_t offset, void *out,
             size_t n) {
  if (!s || !s->on || (!out && n))
    return -EINVAL;
  const uint8_t *p = NULL;
  size_t length = 0;
  if (space == DAC_MEMORY_RAM) {
    p = s->j ? s->j->ram : s->r ? s->r->ram : s->v->ram;
    length = s->r ? sizeof(s->r->ram) : 65536;
  } else if (space == DAC_MEMORY_ROM) {
    p = s->j ? s->j->rom : s->r ? s->r->rom : s->v->rom;
    length = s->r ? sizeof(s->r->rom) : 16384;
  } else if (space == DAC_MEMORY_VIDEO) {
    p = s->j ? s->j->ram + VRAM_BASE : s->r ? s->r->vram : s->v->ram + 0xd800;
    length = s->r ? sizeof(s->r->vram) : 65536 - 0xd800;
  } else
    return -ENOTSUP;
  if (offset > length || n > length - offset)
    return -EINVAL;
  if (n)
    memcpy(out, p + offset, n);
  return 0;
}
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
  free(s->disk_b);
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
int dac_mount_unit(dac_session *s, unsigned unit, const void *p, size_t n,
                   int writable) {
  if (!s || unit > (s->kind == 2 ? 1u : 0u) || s->kind == 1 || (n && !p))
    return -EINVAL;
  if (s->on &&
      (!s->r || s->r->fdc.phase || s->r->fdc.cmd_pos || s->r->fdc.seeking))
    return -EBUSY;
  if (n &&
      (s->kind == 2
           ? robotron_disk_validate(dac_memory_storage((void *)p, n, 0)) != 0
           : (n != JUK_SINGLE_SIDED_SIZE && n != JUK_DOUBLE_SIDED_SIZE)))
    return -EINVAL;
  uint8_t *copy = n ? malloc(n) : NULL;
  if (n && !copy)
    return -ENOMEM;
  if (n)
    memcpy(copy, p, n);
  if (s->on) {
    int r = robotron_disk_unit(s->r, unit,
                               n ? dac_memory_storage(copy, n, !!writable)
                                 : (dac_storage){0},
                               !!writable);
    if (r) {
      free(copy);
      return r;
    }
    s->r->drive[unit].ready = s->r->drive[unit].ready_indexes = 0;
  }
  if (s->r)
    s->r->drive[unit].ejected = 0;
  if (unit) {
    free(s->disk_b);
    s->disk_b = copy;
    s->disk_b_size = n;
    s->writable_b = !!writable;
  } else {
    free(s->disk);
    s->disk = copy;
    s->disk_size = n;
    s->writable = !!writable;
  }
  return 0;
}
int dac_mount(dac_session *s, const void *p, size_t n, int writable) {
  if (!s || s->on)
    return -EINVAL;
  return dac_mount_unit(s, 0, p, n, writable);
}
int dac_power(dac_session *s, int on) {
  if (!s)
    return -EINVAL;
  if (!on) {
    if (s->on && s->r)
      robotron_flush_interrupted_write(s->r);
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
    unsigned ejected[2] = {s->r->drive[0].ejected, s->r->drive[1].ejected};
    unsigned doors[2] = {s->r->drive[0].door_open, s->r->drive[1].door_open};
    unsigned signals = s->r->v24.signals, disconnected = s->r->disconnected;
    unsigned baud = s->r->v24.peer_baud, format = s->r->v24.peer_format;
    unsigned printer_state = s->r->printer_state;
    robotron_init(s->r);
    s->r->printer_state = printer_state;
    s->r->v24.signals = signals;
    s->r->v24.peer_baud = baud;
    s->r->v24.peer_format = format;
    s->r->disconnected = disconnected;
    for (unsigned u = 0; u < 2; u++) {
      s->r->drive[u].door_open = doors[u];
      s->r->drive[u].ejected = ejected[u];
    }
    robotron_load(s->r, s->firmware, s->firmware_size, s->prom, s->prom_size);
    memcpy(s->r->chargen, s->glyphs, s->glyph_size);
    if (s->keyboard_size)
      robotron_keyboard_load(s->r, s->keyboard, s->keyboard_size);
    if (s->disk)
      robotron_disk(s->r,
                    dac_memory_storage(s->disk, s->disk_size, s->writable),
                    s->writable);
    if (s->disk_b)
      robotron_disk_unit(
          s->r, 1, dac_memory_storage(s->disk_b, s->disk_b_size, s->writable_b),
          s->writable_b);
  }
  s->on = 1;
  bind_observer(s);
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
unsigned dac_debug_reg(dac_session *s, unsigned field) {
  if (!s || !s->r || !s->on)
    return 0;
  dac_z80 *c = &s->r->cpu;
  z80_t *r = &c->cpu;
  const uint32_t values[] = {r->pc,
                             r->sp,
                             r->af,
                             r->bc,
                             r->de,
                             r->hl,
                             r->ix,
                             r->iy,
                             r->af2,
                             r->bc2,
                             r->de2,
                             r->hl2,
                             r->im,
                             r->iff1,
                             r->iff2,
                             r->i,
                             r->r,
                             (uint32_t)c->cycles,
                             (uint32_t)(c->cycles >> 32),
                             s->r->bank,
                             !!(c->pins & Z80_HALT),
                             z80_opdone(r),
                             Z80_GET_ADDR(c->pins)};
  return field < sizeof(values) / sizeof(values[0]) ? values[field] : 0;
}
int dac_debug_byte(dac_session *s, unsigned address) {
  return s && s->r && s->on && address < 65536
             ? robotron_peek(s->r, (uint16_t)address)
             : -EINVAL;
}
unsigned dac_debug_map(dac_session *s, unsigned address, unsigned write) {
  return s && s->r && s->on && address < 65536
             ? robotron_mapping(s->r, (uint16_t)address, write)
             : 0;
}
typedef struct {
  dac_session *s;
  uint16_t pc;
  unsigned length, read;
} debug_dasm;
static uint8_t debug_input(void *user) {
  debug_dasm *d = user;
  return d->read++ < 16 ? robotron_peek(d->s->r, d->pc++) : 0;
}
static void debug_output(char c, void *user) {
  debug_dasm *d = user;
  if (d->length < sizeof(d->s->debug_text) - 1)
    d->s->debug_text[d->length++] = c;
}
unsigned dac_debug_disassemble(dac_session *s, unsigned address) {
  if (!s || !s->r || !s->on || address > 65535)
    return 0;
  debug_dasm d = {s, (uint16_t)address, 0, 0};
  unsigned next = z80dasm_op((uint16_t)address, debug_input, debug_output, &d);
  s->debug_text[d.length] = 0;
  return next;
}
const char *dac_debug_text(dac_session *s) { return s ? s->debug_text : NULL; }
unsigned dac_debug_step(dac_session *s) {
  if (!s || !s->r || !s->on)
    return 0;
  unsigned n = 0;
  do {
    robotron_run(s->r, 1);
    n++;
  } while (n < 100000 && !z80_opdone(&s->r->cpu.cpu));
  return n;
}
int dac_debug_break(dac_session *s, unsigned enabled) {
  if (!s || !s->r || !s->on || (enabled && !s->timeline_on))
    return -EINVAL;
  s->debug_break = !!enabled;
  if (!enabled)
    s->debug_exec = 0;
  s->debug_hit = 0;
  return 0;
}
int dac_debug_target(dac_session *s, unsigned address) {
  if (!s || !s->r || !s->on || address > 65535)
    return -EINVAL;
  s->debug_exec = 1;
  s->debug_address = address;
  s->debug_hit = 0;
  return 0;
}
unsigned dac_debug_hit(dac_session *s) { return s ? s->debug_hit : 0; }
unsigned dac_debug_run(dac_session *s, unsigned ticks) {
  if (!s || !s->r || !s->on)
    return 0;
  if (!s->debug_break && !s->debug_exec)
    return dac_run(s, ticks);
  if (ticks > 100000)
    ticks = 100000;
  unsigned n = 0;
  while (n < ticks && !s->debug_hit) {
    robotron_run(s->r, 1);
    n++;
    if (s->debug_exec && z80_opdone(&s->r->cpu.cpu) &&
        Z80_GET_ADDR(s->r->cpu.pins) == s->debug_address)
      s->debug_hit = 2;
  }
  return n;
}
int dac_key(dac_session *s, unsigned key, int down) {
  if (!s || !s->on || key > 255)
    return -EINVAL;
  if (s->j) {
    juku_key(s->j, (uint8_t)key, down);
    return 0;
  }
  if (s->r) {
    if (s->r->disconnected & 1)
      return 0;
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
    if (s->r->disconnected & 2)
      for (unsigned i = 0; i < s->width * s->height; i++)
        s->pixels[i] = 0xff101812;
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
  if (s->r->disconnected & 1)
    return 0;
  return robotron_keyboard_key(&s->r->keyboard, key / 8, key % 8, down);
}
int dac_tap(dac_session *s, unsigned key, unsigned modifiers) {
  if (!s || !s->on || !s->r || !s->r->keyboard_enabled)
    return -EINVAL;
  if (s->r->disconnected & 1)
    return 0;
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

const uint8_t *dac_disk_data_unit(dac_session *s, unsigned u) {
  return s && u < 2 ? (u ? s->disk_b : s->disk) : NULL;
}
unsigned dac_disk_size_unit(dac_session *s, unsigned u) {
  return s && u < 2 ? (unsigned)(u ? s->disk_b_size : s->disk_size) : 0;
}
int dac_drive_inserted(dac_session *s, unsigned u, unsigned inserted) {
  if (!s || !s->r || u > 1 || inserted > 1)
    return -EINVAL;
  if (!s->r->drive[u].door_open)
    return -EBUSY;
  if (inserted && !dac_disk_size_unit(s, u))
    return -ENOENT;
  s->r->drive[u].ejected = !inserted;
  s->r->drive[u].ready = s->r->drive[u].ready_indexes = 0;
  s->r->drive[u].loaded = 0;
  return 0;
}
/* Transfer an ejected image to an open, physically empty drive. If the target
 * retains another ejected image, that image takes the vacated parking slot.
 * Storage, layout and protection travel together; drive mechanics do not. */
int dac_drive_protect(dac_session *s, unsigned unit, unsigned protect) {
  if (!s || !s->r || unit > 1 || protect > 1)
    return -EINVAL;
  if (!dac_disk_size_unit(s, unit))
    return -ENOENT;
  if (!s->r->drive[unit].ejected)
    return -EBUSY;
  int writable = !protect;
  if (unit)
    s->writable_b = writable;
  else
    s->writable = writable;
  dac_media *media = unit ? &s->r->disk_b : &s->r->disk;
  media->writable = writable;
  media->storage = dac_memory_storage(unit ? s->disk_b : s->disk,
                                      dac_disk_size_unit(s, unit), writable);
  return 0;
}
int dac_drive_transfer(dac_session *s, unsigned from, unsigned to) {
  if (!s || !s->r || from > 1 || to > 1)
    return -EINVAL;
  if (from == to)
    return dac_drive_inserted(s, to, 1);
  robotron *r = s->r;
  if (!dac_disk_size_unit(s, from))
    return -ENOENT;
  if (!r->drive[from].ejected || !r->drive[from].door_open ||
      !r->drive[to].door_open ||
      (dac_disk_size_unit(s, to) && !r->drive[to].ejected) ||
      (s->on && (r->fdc.phase || r->fdc.cmd_pos)))
    return -EBUSY;
  uint8_t *bytes = s->disk;
  s->disk = s->disk_b;
  s->disk_b = bytes;
  size_t size = s->disk_size;
  s->disk_size = s->disk_b_size;
  s->disk_b_size = size;
  int writable = s->writable;
  s->writable = s->writable_b;
  s->writable_b = writable;
  dac_media media = r->disk;
  r->disk = r->disk_b;
  r->disk_b = media;
  unsigned format = r->disk_format[0];
  r->disk_format[0] = r->disk_format[1];
  r->disk_format[1] = format;
  for (unsigned i = 0; i < 160; i++) {
    robotron_track track = r->tracks[0][i];
    r->tracks[0][i] = r->tracks[1][i];
    r->tracks[1][i] = track;
  }
  for (unsigned u = 0; u < 2; u++) {
    r->drive[u].ready = r->drive[u].ready_indexes = r->drive[u].loaded = 0;
    r->drive[u].ejected = u != to;
  }
  return 0;
}
int dac_drive_door(dac_session *s, unsigned u, unsigned open) {
  if (!s || !s->r || u > 1 || open > 1)
    return -EINVAL;
  robotron_drive_door(s->r, u, open);
  return 0;
}
unsigned dac_drive_status_unit(dac_session *s, unsigned u) {
  if (!s || !s->r || u > 1)
    return 0;
  robotron *r = s->r;
  unsigned present =
      !r->drive[u].ejected && !!(u ? s->disk_b_size : s->disk_size);
  unsigned writable = u ? s->writable_b : s->writable;
  unsigned base = (writable << 2) | (present << 3) |
                  (r->drive[u].door_open << 5) |
                  ((r->fdc.physical[u] & 255) << 8);
  if (!s->on)
    return base;
  return base | (!(r->motor & (u ? 8 : 128))) |
         ((r->fdc.phase == 2 && r->fdc.unit == u) << 1) |
         (((r->fdc.seeking >> u) & 1) << 4);
}
unsigned dac_drive_phase_unit(dac_session *s, unsigned u) {
  return s && s->r && u < 2 ? s->r->rotation[u] : 0;
}
unsigned dac_drive_steps_unit(dac_session *s, unsigned u) {
  return s && s->r && u < 2 ? s->r->fdc.steps[u] : 0;
}
unsigned dac_drive_detail_unit(dac_session *s, unsigned u) {
  if (!s || !s->r || !s->on || u > 1)
    return 0;
  robotron_fdc *f = &s->r->fdc;
  unsigned selected = f->unit == u, sector = f->sector;
  if (selected && f->phase == 2 && f->read_track && !f->search &&
      f->physical[u] < 80 && f->head < 2) {
    robotron_track *tr = &s->r->tracks[u][f->physical[u] * 2 + f->head];
    if (f->slot < tr->count)
      sector = tr->sector[f->slot].r;
  }
  return selected | ((selected && f->phase == 2) << 1) |
         ((selected && f->phase == 2 && f->write == 1) << 2) |
         (((f->seeking >> u) & 1) << 3) |
         (selected ? (f->head << 4) | (sector << 8) : 0);
}
unsigned dac_drive_position_unit(dac_session *s, unsigned u) {
  return s && s->r ? robotron_head_position(s->r, u) : 0;
}
unsigned dac_drive_mechanics_unit(dac_session *s, unsigned u) {
  if (!s || !s->r || u > 1 || !s->on)
    return 0;
  robotron *r = s->r;
  robotron_drive *d = &r->drive[u];
  return robotron_drive_ready(r, u) |
         ((d->loaded && r->cpu.cycles >= d->load_at) << 1) |
         ((r->cpu.cycles < d->settle_at) << 2) |
         ((!d->door_open && !d->ejected && d->speed && r->rotation[u] < 9984 &&
           (u ? r->disk_b.storage.read : r->disk.storage.read))
          << 3) |
         ((d->speed * 1000u / ROBOTRON_SPINUP_TICKS) << 8);
}
unsigned dac_drive_step_age(dac_session *s, unsigned u, unsigned index) {
  if (!s || !s->r || u > 1 || index >= ROBOTRON_STEP_EVENTS ||
      index >= s->r->fdc.steps[u])
    return UINT32_MAX;
  unsigned n = s->r->fdc.steps[u];
  uint64_t age = s->r->cpu.cycles -
                 s->r->drive[u].events[(n - 1 - index) % ROBOTRON_STEP_EVENTS];
  return age < UINT32_MAX ? (unsigned)age : UINT32_MAX;
}
unsigned dac_drive_diagnostic(dac_session *s, unsigned u, unsigned field) {
  if (!s || !s->r || !s->on || u > 1)
    return 0;
  robotron *r = s->r;
  robotron_fdc *f = &r->fdc;
  robotron_drive *d = &r->drive[u];
  switch (field) {
  case 0:
    return d->index_count;
  case 1: {
    if (!d->loaded)
      return 0;
    unsigned duration = f->head_load_ticks;
    if (duration < ROBOTRON_HEAD_LOAD_TICKS)
      duration = ROBOTRON_HEAD_LOAD_TICKS;
    uint64_t left = d->load_at > r->cpu.cycles ? d->load_at - r->cpu.cycles : 0;
    return left >= duration ? 0
                            : (unsigned)((duration - left) * 65536 / duration);
  }
  case 2:
    return f->unit == u ? f->phase | (f->search << 4) | (f->command[0] << 8)
                        : 0;
  case 3:
    return f->unit == u ? f->data_pos | (f->data_len << 16) : 0;
  case 4:
    return f->unit == u && f->phase == 1 && f->result_len == 7
               ? f->result[0] | (f->result[1] << 8) | (f->result[2] << 16) |
                     0x1000000
               : 0;
  default:
    return 0;
  }
}
int dac_serial_send(dac_session *s, unsigned byte) {
  if (!s || !s->r || !s->on || byte > 255)
    return -EINVAL;
  robotron *r = s->r;
  if (r->v24.count >= 65536)
    return -ENOSPC;
  r->v24.input[(r->v24.read + r->v24.count) % 65536] = (uint8_t)byte;
  r->v24.count++;
  return 0;
}
int dac_serial_signals(dac_session *s, unsigned signals) {
  if (!s || !s->r || signals > 7)
    return -EINVAL;
  robotron_v24_signals(s->r, signals);
  return 0;
}
static int valid_peer(unsigned baud, unsigned format) {
  return baud <= 115200 &&
         (!baud || (baud >= 50 && (format & 15) >= 5 && (format & 15) <= 8 &&
                    ((format >> 4) & 3) <= 2 && ((format >> 8) & 7) >= 2 &&
                    ((format >> 8) & 7) <= 4 && !(format & ~0x73f)));
}
int dac_serial_peer(dac_session *s, unsigned baud, unsigned format) {
  if (!s || !s->r || !valid_peer(baud, format))
    return -EINVAL;
  s->r->v24.peer_baud = baud;
  s->r->v24.peer_format = format;
  s->r->v24.bits = s->r->v24.peer_phase = s->r->v24.decode_phase = 0;
  memset(&s->r->v24.decoder, 0, sizeof(s->r->v24.decoder));
  return 0;
}
unsigned dac_serial_peer_baud(dac_session *s) {
  return s && s->r ? s->r->v24.peer_baud : 0;
}
unsigned dac_serial_peer_format(dac_session *s) {
  return s && s->r ? s->r->v24.peer_format : 0;
}
const uint8_t *dac_serial_decoded_data(dac_session *s) {
  return s && s->r ? s->r->v24.decoded : NULL;
}
unsigned dac_serial_decoded_size(dac_session *s) {
  return s && s->r ? s->r->v24.decoded_size : 0;
}
unsigned dac_serial_decoded_errors(dac_session *s) {
  return s && s->r
             ? s->r->v24.decoder.errors | (s->r->v24.decoded_overflow ? 32 : 0)
             : 0;
}
unsigned dac_serial_errors(dac_session *s) {
  return s && s->r
             ? s->r->rx_b.errors |
                   (s->r->rx_b.count ? s->r->v24.fifo_errors[s->r->rx_b.read]
                                     : 0)
             : 0;
}
void dac_serial_cancel(dac_session *s) {
  if (s && s->r)
    s->r->v24.count = 0;
}
unsigned dac_circuit_activity(dac_session *s, unsigned field) {
  if (!s || !s->r)
    return 0;
  robotron *r = s->r;
  switch (field) {
  case 0:
    return (unsigned)r->cpu.cycles;
  case 1:
    return r->dma.transferred;
  case 2:
    return r->serial_events;
  case 3:
    return r->fdc.data_pos;
  default:
    return 0;
  }
}
unsigned dac_serial_status(dac_session *s) {
  return s && s->r ? s->r->v24.signals | (s->r->v24.count << 8) : 0;
}
const uint8_t *dac_serial_data(dac_session *s) {
  return s && s->r ? s->r->v24.output : NULL;
}
unsigned dac_serial_size(dac_session *s) {
  return s && s->r ? s->r->v24.size : 0;
}
unsigned dac_serial_overflow(dac_session *s) {
  return s && s->r ? s->r->v24.overflow : 0;
}
void dac_serial_clear(dac_session *s) {
  if (s && s->r) {
    s->r->v24.size = s->r->v24.overflow = 0;
    s->r->v24.decoded_size = s->r->v24.decoded_overflow =
        s->r->v24.decoder.errors = 0;
  }
}
int dac_cables(dac_session *s, unsigned value) {
  if (!s || !s->r || value > 3)
    return -EINVAL;
  robotron *r = s->r;
  if ((value ^ r->disconnected) & 1) {
    if (r->keyboard_enabled) {
      uint8_t rom[2048];
      memcpy(rom, r->keyboard.rom, sizeof(rom));
      robotron_keyboard_init(&r->keyboard, rom, r, robotron_serial_clock);
    }
    r->key_read = r->key_write = 0;
  }
  r->disconnected = value;
  return 0;
}
unsigned dac_cable_status(dac_session *s) {
  return s && s->r ? s->r->disconnected : 0;
}
int dac_printer_state(dac_session *s, unsigned state) {
  if (!s || !s->r || state > 3)
    return -EINVAL;
  robotron_printer_state(s->r, state);
  return 0;
}
unsigned dac_printer_status(dac_session *s) {
  return s && s->r ? s->r->printer_state : 0;
}
unsigned dac_printer_dropped(dac_session *s) {
  return s && s->r ? s->r->printer_dropped : 0;
}
const uint8_t *dac_printer_data(dac_session *s) {
  return s && s->r ? s->r->printer : NULL;
}
unsigned dac_printer_size(dac_session *s) {
  return s && s->r ? s->r->printer_size : 0;
}
unsigned dac_printer_overflow(dac_session *s) {
  return s && s->r ? s->r->printer_overflow : 0;
}
void dac_printer_clear(dac_session *s) {
  if (s && s->r)
    s->r->printer_size = s->r->printer_overflow = 0;
}

/* Internal, same-build snapshots. The browser keys these by the WASM hash.
 * No pointers are persisted; CRC detects corruption, bounds reject bad state.
 * Restore is atomic and requires the same firmware, disk size and write mode.
 */
typedef struct {
  uint32_t magic, version, size, disk_size, writable, disk_b_size, writable_b,
      crc;
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
static unsigned other_state_size(dac_session *s);
static int other_state_save(dac_session *s, void *p, size_t n);
static int other_state_load(dac_session *s, const void *p, size_t n);
unsigned dac_state_size(dac_session *s) {
  if (s && !s->r)
    return other_state_size(s);
  return s && s->r && s->on
             ? (unsigned)(sizeof(state_header) + sizeof(robotron) +
                          s->disk_size + s->disk_b_size)
             : 0;
}
int dac_state_save(dac_session *s, void *p, size_t n) {
  if (s && !s->r)
    return other_state_save(s, p, n);
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
  memset(&copy->disk_b, 0, sizeof(copy->disk_b));
  uint8_t *payload = (uint8_t *)p + sizeof(state_header);
  memcpy(payload, copy, sizeof(*copy));
  free(copy);
  if (s->disk_size)
    memcpy(payload + sizeof(robotron), s->disk, s->disk_size);
  if (s->disk_b_size)
    memcpy(payload + sizeof(robotron) + s->disk_size, s->disk_b,
           s->disk_b_size);
  state_header h = {0x44414353,
                    13,
                    (uint32_t)n,
                    (uint32_t)s->disk_size,
                    (uint32_t)s->writable,
                    (uint32_t)s->disk_b_size,
                    (uint32_t)s->writable_b,
                    state_crc(payload, n - sizeof(h))};
  memcpy(p, &h, sizeof(h));
  return 0;
}
static int valid_cpu(const dac_z80 *c) {
  return c->cpu.step <= 1708 && c->cpu.hlx_idx < 3 && c->cpu.im < 3;
}
int dac_state_load(dac_session *s, const void *p, size_t n) {
  if (s && !s->r)
    return other_state_load(s, p, n);
  if (!s || !s->r || !p || n < sizeof(state_header) + sizeof(robotron))
    return -EINVAL;
  state_header h;
  memcpy(&h, p, sizeof(h));
  if (h.magic != 0x44414353 || h.version != 13 || h.size != n ||
      h.disk_size != s->disk_size || h.disk_b_size != s->disk_b_size ||
      h.writable_b != (unsigned)s->writable_b ||
      h.writable != (unsigned)s->writable ||
      n != sizeof(h) + sizeof(robotron) + s->disk_size + s->disk_b_size)
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
      r->raster.fraction >= 104 || r->raster.character > 3584 ||
      r->raster.row >= 28 || r->raster.stream >= 1920 ||
      r->raster.remaining > 1 || r->raster.overflow > 1 ||
      r->raster.stopped > 2 || r->raster.underrun > 1 ||
      r->raster.fetch_col > 80 || r->raster.fetch_columns > 80 ||
      (r->raster.remaining &&
       (!r->raster.fetch_columns ||
        r->raster.fetch_col >= r->raster.fetch_columns)) ||
      r->raster.fetch_fifo > 80 || r->raster.fetch_phase > 2 ||
      r->raster.fetch_ignored > 2 || r->raster.fetch_invisible > 1 ||
      r->raster.fetch_wait > 55 || r->raster.pending_valid > 1 ||
      r->raster.valid_rows >= (1u << 24) || r->raster.field > 63 ||
      r->raster.end_screen > 1 || r->raster.blank_from > 24 ||
      r->raster.dma > 31 || r->raster.ignored > 1 || !valid_cpu(&r->cpu) ||
      !valid_cpu(&k->cpu) || f->unit >= 4 || f->phase > 2 || f->write > 2 ||
      f->formatting > 1 || f->search > 6 || f->read_track > 1 ||
      f->track_count > 256 || f->track_match > 1 || f->track_st1 > 255 ||
      f->track_st2 > 255 || (f->write_fault && f->write_fault != 0x10) ||
      (f->phase == 2 && f->n > 5) ||
      (f->search == 6 && (!f->formatting || !f->data_pos || f->data_pos % 4)) ||
      (f->search == 4 && !f->read_track) || f->read_id > 1 ||
      f->slot >= ROBOTRON_TRACK_SECTORS || f->id_head > 255 ||
      f->error2 > 255 || f->head_load_ticks > 1022362 ||
      f->head_unload_ticks > 1022362 ||
      (f->phase == 2 &&
       (f->unit > 1 || !(f->unit ? s->disk_b_size : s->disk_size))) ||
      f->cmd_len > 9 || f->cmd_pos >= 9 || f->result_len > 7 ||
      f->result_pos > f->result_len ||
      (f->phase == 1 && f->result_pos >= f->result_len) ||
      f->data_len > sizeof(f->data) || f->data_pos > f->data_len ||
      (f->phase == 2 && f->data_pos >= f->data_len &&
       !(f->formatting && f->search == 6)) ||
      r->dma.auto_restart > 1 || r->dma.mode > 3 || r->dma.bus_owned > 1 ||
      r->dma.release > 2 || r->v24.tx_div > 64 || r->v24.tx_elapsed > 768 ||
      r->v24.decode_phase >= 3993600 || r->v24.decoded_size > 65536 ||
      r->v24.decoder.phase > 4 || r->v24.decoder.bits > 8 ||
      r->v24.decoder.wait > 64 || r->v24.break_active > 1 ||
      r->v24.break_latched > 1 || r->v24.rx_locked > 1 ||
      r->dma.operation > 3 || r->dma.stop_match > 1 ||
      r->dma.wait_enabled > 1 || r->dma.wait > 1 || r->dma.phase > 2 ||
      r->dma.ticks > 4 || (r->dma.phase && !r->dma.ticks) ||
      (!r->dma.phase && r->dma.ticks) || r->dma.tag_count > 10 ||
      r->dma.tag_pos > r->dma.tag_count ||
      (r->dma.tag_count && r->dma.tag_pos >= r->dma.tag_count) ||
      r->dma.read_pos >= 7 || r->sio_pointer[0] > 7 || r->sio_pointer[1] > 7 ||
      r->v24.read >= 65536 || r->v24.count > 65536 || r->v24.size > 65536 ||
      r->v24.full > 1 || r->v24.pending > 1 || r->v24.in_service > 1 ||
      r->v24.overflow > 1 ||
      !valid_peer(r->v24.peer_baud, r->v24.peer_format) ||
      r->v24.peer_phase >= 3993600 || r->v24.ext_pending > 1 ||
      r->v24.ext_service > 1 || r->v24.ext_latched > 1 ||
      r->v24.ext_signals > 7 || (r->v24.frame_errors & ~0x40) ||
      (r->v24.fifo_errors[0] & ~0x40) || (r->v24.fifo_errors[1] & ~0x40) ||
      (r->v24.fifo_errors[2] & ~0x40) || r->rx_b.wait > 64 ||
      r->v24.frame >= (1u << 24) || r->v24.signals > 7 || r->v24.bits > 24 ||
      r->v24.clocks > 64 || r->v24.tx_clocks > 768 || r->v24.tx_halves > 1536 ||
      r->tx_halves > 1536 || r->v24.tx_clocks != (r->v24.tx_halves + 1) / 2 ||
      r->tx_clocks != (r->tx_halves + 1) / 2 || r->v24.tx_subclock > 1 ||
      r->serial_levels[0] > 1 || r->serial_levels[1] > 1 ||
      r->serial_levels[2] > 1 || r->serial_levels[3] > 1 || r->rx_b.read >= 3 ||
      r->rx_b.count > 3 || r->rx_b.phase > 4 || r->rx_b.bits > 8 ||
      r->disconnected > 3 || r->rx.read >= 3 || r->rx.count > 3 ||
      r->rx.phase > 4 || r->rx.bits > 8 || k->tap_read >= 64 ||
      k->tap_count > 64 || k->tap_phase > 2 || r->tx_pending > 1 ||
      r->tx_in_service > 1 || k->clock_fraction >= 3993600 ||
      r->key_write - r->key_read > 256 ||
      r->printer_size > sizeof(r->printer) || r->printer_state > 3 ||
      r->printer_accept > 1 || r->printer_ext_pending > 1 ||
      r->printer_ext_service > 1 || r->printer_ext_latched > 1 ||
      r->printer_cts_latched > 1 ||
      (f->formatting &&
       (f->data_len != f->command[3] * 4 || !f->command[3] ||
        f->command[3] > ROBOTRON_TRACK_SECTORS || f->write != 1)) ||
      f->head > 1;
  for (unsigned u = 0; u < 2; u++)
    invalid |= r->rotation[u] >= ROBOTRON_REVOLUTION_TICKS ||
               r->drive[u].speed > ROBOTRON_SPINUP_TICKS ||
               r->drive[u].fraction >= ROBOTRON_SPINUP_TICKS ||
               r->drive[u].ready_indexes > 2 || r->drive[u].ready > 1 ||
               r->drive[u].ejected > 1 || r->drive[u].door_open > 1 ||
               r->drive[u].loaded > 1 || r->drive[u].from_q16 > 79 * 65536u;
  for (unsigned u = 0; u < 4; u++)
    invalid |= f->cylinder[u] > 255 || f->seek_target[u] > 255 ||
               f->physical[u] > 79 || f->recalibrate[u] > 1 ||
               f->pulses[u] > 255 ||
               ((f->seeking & (1u << u)) &&
                (!f->seek_interval[u] || f->seek_interval[u] > 16 * 3994));
  for (unsigned i = 0; i < 64; i++)
    invalid |= k->taps[i] >= 104 || k->tap_mods[i] > 3;
  if (s->disk_size)
    invalid |=
        robotron_disk_unit(r, 0,
                           dac_memory_storage((void *)(payload + sizeof(*r)),
                                              s->disk_size, s->writable),
                           s->writable) != 0;
  if (s->disk_b_size)
    invalid |=
        robotron_disk_unit(
            r, 1,
            dac_memory_storage((void *)(payload + sizeof(*r) + s->disk_size),
                               s->disk_b_size, s->writable_b),
            s->writable_b) != 0;
  if (f->phase == 2 && (f->search == 0 || f->search == 3 || f->search == 5) &&
      !f->formatting && f->unit < 2 && f->head < 2 && f->physical[f->unit] < 80)
    invalid |=
        f->slot >= r->tracks[f->unit][f->physical[f->unit] * 2 + f->head].count;
  for (unsigned row = 0; row < 24; row++) {
    const robotron_video_row *out = &r->raster.scanout[row];
    invalid |= out->columns > 80 || out->lines > 16;
    for (unsigned col = 0; col < 80; col++)
      for (unsigned line = 0; line < 16; line++)
        invalid |= out->highlight[col][line] > 1;
  }
  if (invalid) {
    free(r);
    return -EINVAL;
  }
  /* Repair all host callbacks from code, never from serialized addresses. */
  robotron_rebind(r);
  r->trace_master = DAC_MASTER_CPU;
  if (s->disk_size) {
    memcpy(s->disk, payload + sizeof(*r), s->disk_size);
    r->disk.storage = dac_memory_storage(s->disk, s->disk_size, s->writable);
  } else
    memset(&r->disk, 0, sizeof(r->disk));
  if (s->disk_b_size) {
    memcpy(s->disk_b, payload + sizeof(*r) + s->disk_size, s->disk_b_size);
    r->disk_b.storage =
        dac_memory_storage(s->disk_b, s->disk_b_size, s->writable_b);
  } else
    memset(&r->disk_b, 0, sizeof(r->disk_b));
  free(s->r);
  s->r = r;
  s->on = 1;
  bind_observer(s);
  return 0;
}

/* Juku/VJUGA snapshots have the same outer integrity contract. A fresh core
 * supplies callbacks; serialized host pointers are always cleared/replaced. */
static unsigned other_state_size(dac_session *s) {
  return s && s->on
             ? (unsigned)(sizeof(state_header) +
                          (s->j ? sizeof(juku) : sizeof(vjuga)) + s->disk_size)
             : 0;
}
static int other_state_save(dac_session *s, void *p, size_t n) {
  if (!p || !other_state_size(s) || n != other_state_size(s))
    return -EINVAL;
  size_t size = s->j ? sizeof(juku) : sizeof(vjuga);
  void *copy = malloc(size);
  if (!copy)
    return -ENOMEM;
  memcpy(copy, s->j ? (void *)s->j : (void *)s->v, size);
  if (s->j) {
    juku *j = copy;
    j->cpu.read_byte = NULL;
    j->cpu.write_byte = NULL;
    j->cpu.port_in = NULL;
    j->cpu.port_out = NULL;
    j->cpu.userdata = NULL;
    memset(&j->hooks, 0, sizeof(j->hooks));
    memset(&j->bus_trace, 0, sizeof(j->bus_trace));
    j->kbd_str = NULL;
    j->fdc.disk = NULL;
    j->disk.fp = j->disk.deleted_marks_fp = NULL;
    memset(&j->disk.media.storage, 0, sizeof(j->disk.media.storage));
    memset(&j->disk.marks, 0, sizeof(j->disk.marks));
  } else
    memset(&((vjuga *)copy)->cpu.bus, 0, sizeof(dac_z80_bus));
  uint8_t *payload = (uint8_t *)p + sizeof(state_header);
  memcpy(payload, copy, size);
  free(copy);
  if (s->disk_size)
    memcpy(payload + size, s->disk, s->disk_size);
  state_header h = {0x44414353,
                    10 + s->kind,
                    (uint32_t)n,
                    (uint32_t)s->disk_size,
                    (uint32_t)s->writable,
                    0,
                    0,
                    state_crc(payload, n - sizeof(h))};
  memcpy(p, &h, sizeof(h));
  return 0;
}
static int other_state_load(dac_session *s, const void *p, size_t n) {
  size_t size = s->j ? sizeof(juku) : sizeof(vjuga);
  if (!p || n != sizeof(state_header) + size + s->disk_size)
    return -EINVAL;
  state_header h;
  memcpy(&h, p, sizeof(h));
  const uint8_t *payload = (const uint8_t *)p + sizeof(h);
  if (h.magic != 0x44414353 || h.version != 10 + s->kind || h.size != n ||
      h.disk_size != s->disk_size || h.writable != (unsigned)s->writable ||
      h.disk_b_size || h.writable_b ||
      h.crc != state_crc(payload, n - sizeof(h)))
    return -EINVAL;
  if (s->v) {
    vjuga *v = malloc(sizeof(*v));
    if (!v)
      return -ENOMEM;
    memcpy(v, payload, sizeof(*v));
    if (!valid_cpu(&v->cpu) || v->decode_mode > 1 ||
        memcmp(v->rom, s->firmware, 16384)) {
      free(v);
      return -EINVAL;
    }
    vjuga *fresh = malloc(sizeof(*fresh));
    if (!fresh) {
      free(v);
      return -ENOMEM;
    }
    vjuga_init(fresh, v->decode_mode);
    v->cpu.bus = fresh->cpu.bus;
    v->cpu.bus.user = v;
    free(fresh);
    free(s->v);
    s->v = v;
  } else {
    juku *j = malloc(sizeof(*j));
    if (!j)
      return -ENOMEM;
    memcpy(j, payload, sizeof(*j));
    juku_fdc *f = &j->fdc;
    int bad =
        !j->frame_cyc || memcmp(j->rom, s->firmware, 16384) ||
        j->video_modx_sequence >= 6 || j->video_stock_sequence >= 5 ||
        j->video_64_sequence >= 5 || !j->video_stride || j->video_stride > 80 ||
        !j->video_lines || j->video_lines > 384 ||
        j->video_stride * j->video_lines > 10240 || j->mode < 0 ||
        j->mode > 3 || j->console_len < 0 || j->console_len >= CONSOLE_QUEUE ||
        j->console_visible_len < 0 || j->console_visible_len > CONSOLE_QUEUE ||
        f->buffer_len > sizeof(f->buffer) || f->buffer_pos > f->buffer_len ||
        f->write_track_field_pos > sizeof(f->buffer) ||
        (f->write_track_state == 1 && f->write_track_field_pos >= 4) ||
        (f->write_track_state == 3 &&
         f->write_track_field_pos >= JUK_SECTOR_SIZE) ||
        f->write_track_pending_sector < 0 ||
        f->write_track_pending_sector > 10 || f->write_track_state < 0 ||
        f->write_track_state > 4;
    if (bad) {
      free(j);
      return -EINVAL;
    }
    juku *fresh = juku_create();
    if (!fresh) {
      free(j);
      return -ENOMEM;
    }
    j->cpu.read_byte = fresh->cpu.read_byte;
    j->cpu.write_byte = fresh->cpu.write_byte;
    j->cpu.port_in = fresh->cpu.port_in;
    j->cpu.port_out = fresh->cpu.port_out;
    j->cpu.userdata = j;
    free(fresh);
    memset(&j->hooks, 0, sizeof(j->hooks));
    memset(&j->bus_trace, 0, sizeof(j->bus_trace));
    j->kbd_str = NULL;
    j->fdc.disk = &j->disk;
    j->disk.fp = j->disk.deleted_marks_fp = NULL;
    memset(&j->disk.marks, 0, sizeof(j->disk.marks));
    memset(&j->disk.media, 0, sizeof(j->disk.media));
    if (s->disk_size) {
      unsigned heads = s->disk_size == JUK_DOUBLE_SIDED_SIZE ? 2 : 1;
      dac_media_init(&j->disk.media,
                     dac_memory_storage(s->disk, s->disk_size, s->writable),
                     (dac_geometry){80, heads, 10, 512, 1}, s->writable);
      j->disk.heads = heads;
      j->disk.size = s->disk_size;
      j->disk.writable = s->writable;
    }
    free(s->j);
    s->j = j;
  }
  if (s->disk_size)
    memcpy(s->disk, payload + size, s->disk_size);
  s->on = 1;
  bind_observer(s);
  return 0;
}
