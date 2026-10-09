#include "juku_internal.h"
#include "media.h"
#include "trace.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct { unsigned events; uint64_t last_cycle; } observer;
static void observe(void *p, const dac_trace_event *event) {
  observer *o = p;
  assert(event->cycle >= o->last_cycle);
  assert(event->source == 0);
  o->last_cycle = event->cycle;
  o->events++;
}

static void instances(void) {
  juku *a = juku_create(), *b = juku_create();
  assert(a && b);
  uint8_t program[] = {0x3e, 0x12, 0x32, 0x23, 0xc1, 0x76};
  assert(juku_load_rom(a, program, sizeof(program)) == 0);
  program[1] = 0x34;
  assert(juku_load_rom(b, program, sizeof(program)) == 0);
  observer oa = {0}, ob = {0};
  a->bus_trace = (dac_trace_sink){observe, &oa, 0, 3};
  b->bus_trace = (dac_trace_sink){observe, &ob, 0, 0};
  juku_step(a);
  assert(a->cpu.a == 0x12 && b->cpu.a == 0 && b->cpu.cyc == 0);
  juku_step(b);
  assert(b->cpu.a == 0x34);
  assert(juku_run(a, 100) > 0);
  assert(a->ram[0xc123] == 0x12 && b->ram[0xc123] == 0);
  assert(juku_run(b, 100) > 0);
  assert(b->ram[0xc123] == 0x34 && a->ram[0xc123] == 0x12);
  assert(oa.events == 3 && ob.events > 3);
  assert(juku_load_rom(a, program, sizeof(program)) == -EBUSY);
  a->frame_cyc = 40000;
  assert(juku_run(a, 100) == 0); /* halted execution remains bounded */
  unsigned stride, lines;
  assert(juku_video(a, &stride, &lines) == a->ram + VRAM_BASE);
  assert(stride == 40 && lines == 241);
  juku_key(b, 'a', 1); b->kbd_col = 5;
  assert(!(juku_kbd_portb(b, &b->cpu) & 1));
  juku_key(b, 0, 0);
  assert(juku_kbd_portb(b, &b->cpu) & 1);
  juku_destroy(a);
  juku_step(b); /* destruction of another instance cannot invalidate callbacks */
  juku_destroy(b);
}

static void media(void) {
  uint8_t bytes[2048] = {0}, sector[256];
  memset(sector, 0xa5, sizeof(sector));
  dac_media m;
  dac_geometry g = {2, 2, 2, 256, 5};
  assert(dac_media_init(&m, dac_memory_storage(bytes, sizeof(bytes), 1), g, 1) == 0);
  uint64_t offset;
  assert(dac_media_offset(&m, 1, 1, 6, &offset) == 0 && offset == 1792);
  assert(dac_media_write(&m, 1, 1, 6, sector) == 0);
  assert(bytes[1791] == 0 && bytes[1792] == 0xa5 && bytes[2047] == 0xa5);
  memset(sector, 0, sizeof(sector));
  assert(dac_media_read(&m, 1, 1, 6, sector) == 0 && sector[255] == 0xa5);
  assert(dac_media_offset(&m, 2, 0, 5, &offset) == -EINVAL);
  assert(dac_media_offset(&m, 0, 2, 5, &offset) == -EINVAL);
  assert(dac_media_offset(&m, 0, 0, 4, &offset) == -EINVAL);
  assert(dac_media_offset(&m, 0, 0, 7, &offset) == -EINVAL);
  assert(dac_media_init(&m, dac_memory_storage(bytes, sizeof(bytes), 0), g, 0) == 0);
  assert(dac_media_write(&m, 0, 0, 5, sector) == -EROFS);
  assert(dac_media_init(&m, dac_memory_storage(bytes, 17, 1), g, 1) == -EINVAL);
  g = (dac_geometry){1, 1, 4, 512, 1};
  assert(dac_media_init(&m, dac_memory_storage(bytes, sizeof(bytes), 1), g, 1) == 0);
  assert(dac_media_offset(&m, 0, 0, 4, &offset) == 0 && offset == 1536);
  g = (dac_geometry){UINT32_MAX, UINT32_MAX, UINT32_MAX, UINT32_MAX, 1};
  assert(dac_media_init(&m, dac_memory_storage(bytes, sizeof(bytes), 1), g, 1) == -EOVERFLOW);

  uint8_t *image = calloc(1, JUK_SINGLE_SIDED_SIZE);
  assert(image);
  juk_disk disk;
  assert(juk_disk_bind(&disk, dac_memory_storage(image, JUK_SINGLE_SIDED_SIZE, 1), 1, 1) == 0);
  uint8_t juku_sector[JUK_SECTOR_SIZE];
  memset(juku_sector, 0x5a, sizeof(juku_sector));
  assert(juk_disk_write_sector(&disk, 79, 0, 10, juku_sector) == 0);
  assert(image[JUK_SINGLE_SIDED_SIZE - 1] == 0x5a);
  assert(juk_disk_set_sector_deleted(&disk, 79, 0, 10, 1) == 0);
  assert(juk_disk_sector_deleted(&disk, 79, 0, 10) == 1);
  juku_fdc fdc;
  juku_fdc_init(&fdc, &disk);
  assert(fdc.enabled); /* no FILE pointer is required by the controller */
  free(image);
}

int main(void) {
  instances();
  media();
  puts("PASS: independent Juku instances, bounded stepping, trace limits, parameterized media and memory-backed Juku disk");
  return 0;
}
