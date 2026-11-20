/* Actual boot-ROM execution with optional RAM faults and native raster capture.
 * Usage: boot glyphs output-directory seconds
 * [clean|screen|work|alias|dead|reset]. */
#include "../../machines/robotron1715/pc1715.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static const char *fault;
static unsigned bad(unsigned a) {
  return !strcmp(fault, "dead") || (!strcmp(fault, "screen") && a >= 0xf800) ||
         (!strcmp(fault, "work") && a >= 0xf700 && a < 0xf800);
}
static uint16_t mapped(uint16_t a) {
  return !strcmp(fault, "alias") && a >= 0xf700 && a < 0xf800 ? a + 0x100 : a;
}
static uint8_t read_ram(void *p, uint16_t a) {
  pc1715 *m = p;
  if (m->rom_enabled && a < 2048)
    return pc1715_read(p, a);
  return bad(a) ? 0 : pc1715_read(p, mapped(a));
}
static void write_ram(void *p, uint16_t a, uint8_t d) {
  if (!bad(a))
    pc1715_write(p, mapped(a), d);
}
static void load(const char *path, void *p, size_t n) {
  FILE *f = fopen(path, "rb");
  if (!f || fread(p, 1, n, f) != n || fgetc(f) != EOF) {
    fprintf(stderr, "bad image %s\n", path);
    exit(2);
  }
  fclose(f);
}
static unsigned unexpected;
static void external_write(void *p, uint16_t a, uint8_t d) {
  (void)p;
  (void)a;
  (void)d;
  unexpected++;
}
static void capture(pc1715 *m, const char *directory, unsigned index) {
  char path[1024];
  snprintf(path, sizeof(path), "%s/frame-%02u.ppm", directory, index);
  FILE *f = fopen(path, "wb");
  if (!f) {
    perror(path);
    exit(2);
  }
  fprintf(f, "P6\n640 288\n255\n");
  for (unsigned i = 0; i < 640 * 288; i++) {
    uint32_t v = m->video.pixels[i];
    uint8_t rgb[3] = {v >> 16, v >> 8, v};
    fwrite(rgb, 1, 3, f);
  }
  fclose(f);
}
int main(int argc, char **argv) {
  if (argc < 5 || argc > 6)
    return 2;
  fault = argc == 6 ? argv[5] : "clean";
  if (strcmp(fault, "clean") && strcmp(fault, "screen") &&
      strcmp(fault, "work") && strcmp(fault, "alias") &&
      strcmp(fault, "dead") && strcmp(fault, "reset"))
    return 2;
  pc1715 *m = calloc(1, sizeof(*m));
  if (!m)
    return 2;
  pc1715_init(m);
  uint8_t rom[2048], glyphs[4096];
  load(argv[1], rom, 2048);
  load(argv[2], glyphs, 4096);
  pc1715_load(m, rom, 2048);
  pc1715_video_load(m, glyphs, 4096);
  pc1715_card card = {.write = external_write};
  pc1715_attach(m, &card);
  uint32_t random = 0x1715abcd;
  for (unsigned i = 0; i < 65536; i++) {
    random ^= random << 13;
    random ^= random >> 17;
    random ^= random << 5;
    m->ram[i] = random;
  }
  m->cpu.bus.read = read_ram;
  m->cpu.bus.write = write_ram;
  uint64_t until = (uint64_t)(atof(argv[4]) * PC1715_CLOCK_HZ), started = 0;
  unsigned previous = 255, index = 0, saved = 0, reset_done = 0;
  uint64_t checkpoint = 10ull * PC1715_CLOCK_HZ;
  printf("{\"clock_hz\":%u,\"transitions\":[", PC1715_CLOCK_HZ);
  for (uint64_t t = 0; t < until; t += 1000) {
    if (!strcmp(fault, "reset") && !reset_done && t >= PC1715_CLOCK_HZ) {
      pc1715_reset(m);
      m->cpu.bus.read = read_ram;
      m->cpu.bus.write = write_ram;
      previous = 255;
      reset_done = 1;
    }
    pc1715_run(m, 1000);
    if (m->cpu.cycles >= checkpoint) {
      capture(m, argv[3], 100 + (unsigned)(checkpoint / PC1715_CLOCK_HZ));
      checkpoint += 10ull * PC1715_CLOCK_HZ;
    }
    if (m->video.running) {
      unsigned id = m->ram[m->cpu.cpu.iy];
      if (id != previous) {
        if (index)
          printf(",");
        printf("{\"pattern\":%u,\"cycle\":%llu,\"screen\":%u,\"work\":%u}", id,
               (unsigned long long)m->cpu.cycles, m->cpu.cpu.ix, m->cpu.cpu.iy);
        previous = id;
        started = m->video.frames;
        saved = 0;
        index++;
      }
      if (!saved && m->video.frames >= started + 3) {
        capture(m, argv[3], index - 1);
        saved = 1;
      }
    }
  }
  printf("],\"frames\":%llu,\"fetches\":%llu,\"underruns\":%llu,\"overflows\":%"
         "llu,\"unexpected_io\":%u,\"unclaimed_reads\":%llu,\"rom_enabled\":%u,"
         "\"pc\":%u,\"sp\":%u}\n",
         (unsigned long long)m->video.frames,
         (unsigned long long)m->video.fetches,
         (unsigned long long)m->video.underruns,
         (unsigned long long)m->video.overflows, unexpected,
         (unsigned long long)m->unclaimed_reads, m->rom_enabled, m->cpu.cpu.pc,
         m->cpu.cpu.sp);
  free(m);
  return 0;
}
