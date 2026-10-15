/* Original bounded diagnostics; no reference-emulator implementation code. */
#include "../../machines/robotron1715m/robotron.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned ports[128], values[128], count;
static void trace(void *unused, const dac_trace_event *e) {
  (void)unused;
  if (!strcmp(e->kind, "IW") && count < 128) {
    ports[count] = e->address & 255;
    values[count++] = e->data;
  }
}
static int load(const char *path, void *p, unsigned size) {
  FILE *f = fopen(path, "rb");
  if (!f)
    return 0;
  int ok = fread(p, 1, size, f) == size && fgetc(f) == EOF;
  fclose(f);
  return ok;
}
int main(int argc, char **argv) {
  if (argc != 4)
    return 2;
  robotron *m = malloc(sizeof(*m));
  if (!m)
    return 2;
  robotron_init(m);
  uint8_t keyboard[2048];
  if (!load(argv[1], m->rom, 2048) || !load(argv[2], m->prom, 256) ||
      !load(argv[3], keyboard, 2048))
    return 2;
  robotron_keyboard_load(m, keyboard, sizeof(keyboard));
  m->trace = (dac_trace_sink){trace, 0, 0, 0};
  robotron_run(m, 400000);
  const unsigned addresses[] = {0x4000, 0x4001, 0x5000, 0x5001, 0x6000,
                                0x3000, 0x3001, 0x3002, 0x6003};
  for (unsigned i = 0; i < sizeof(addresses) / sizeof(*addresses); i++)
    printf("%04x %02x\n", addresses[i], robotron_read(m, addresses[i]));
  for (unsigned b = 1; b < 8; b++) {
    robotron_output(m, 0x24, b * 17);
    robotron_write(m, 0x7000, 0xa0 + b);
  }
  for (unsigned b = 0; b < 8; b++) {
    robotron_output(m, 0x24, b);
    printf("BANK %u %02x\n", b, robotron_read(m, 0x7000));
  }
  robotron_output(m, 0x24, 0);
  robotron_output(m, 0x1d, 0xff);
  printf("FDC %02x\n", robotron_input(m, 0x1d));
  robotron_output(m, 0x0f, 0x18);
  robotron_output(m, 0x0f, 1);
  printf("SIO-RR1 %02x\n", robotron_input(m, 0x0f));
  for (unsigned i = 0; i < count; i++)
    printf("IO %02x %02x\n", ports[i], values[i]);
  free(m);
  return 0;
}
