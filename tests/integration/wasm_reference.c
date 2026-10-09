#include "../../runners/browser/dac.h"
#include <stdio.h>
#include <stdlib.h>
static int load(dac_session *s, unsigned slot, const char *path) {
  FILE *f = fopen(path, "rb");
  if (!f)
    return -1;
  uint8_t data[16384];
  size_t n = fread(data, 1, sizeof(data), f);
  int extra = fgetc(f);
  fclose(f);
  return extra == EOF ? dac_load(s, slot, data, n) : -1;
}
int main(int argc, char **argv) {
  if (argc != 6) {
    fprintf(stderr, "usage: reference ROM PROM DISK PIXELS TICKS\n");
    return 2;
  }
  dac_session *s = dac_create(2);
  if (!s || load(s, 0, argv[1]) || load(s, 1, argv[2]))
    return 2;
  FILE *f = fopen(argv[3], "rb");
  uint8_t *disk = malloc(819200);
  if (!f || !disk)
    return 2;
  size_t n = fread(disk, 1, 819200, f);
  fclose(f);
  if (n != 819200 || dac_mount(s, disk, n, 1) || dac_power(s, 1))
    return 2;
  free(disk);
  unsigned ticks = (unsigned)strtoul(argv[5], 0, 0);
  while (ticks) {
    unsigned slice = ticks > 100000 ? 100000 : ticks;
    ticks -= dac_run(s, slice);
  }
  const uint32_t *pixels = dac_video(s);
  f = fopen(argv[4], "wb");
  if (!f)
    return 2;
  int ok = fwrite(pixels, 4, dac_width(s) * dac_height(s), f) ==
           dac_width(s) * dac_height(s);
  fclose(f);
  dac_destroy(s);
  return ok ? 0 : 1;
}
