#include "../../machines/robotron1715m/robotron.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static int load(const char *path, void *p, size_t n) {
  FILE *f = fopen(path, "rb");
  if (!f)
    return 0;
  int ok = fread(p, 1, n, f) == n && fgetc(f) == EOF;
  fclose(f);
  return ok;
}
static void trace(void *p, const dac_trace_event *e) {
  (void)p;
  if (!strcmp(e->kind, "IW"))
    fprintf(stderr, "%llu %02x %02x\n", (unsigned long long)e->cycle,
            e->address & 255, e->data);
}
int main(int argc, char **argv) {
  if (argc < 4) {
    fprintf(stderr,
            "usage: %s ROM CAS-PROM DISK [ticks] [keys] [--writable] [--export "
            "PATH]\n",
            argv[0]);
    return 2;
  }
  robotron *m = malloc(sizeof(*m));
  uint8_t *disk = malloc(819200);
  if (!m || !disk)
    return 2;
  robotron_init(m);
  if (getenv("DAC_TRACE_IO"))
    m->trace = (dac_trace_sink){trace, 0, 0, 0};
  if (!load(argv[1], m->rom, 2048) || !load(argv[2], m->prom, 256) ||
      !load(argv[3], disk, 819200))
    return 2;
  int writable = 0;
  const char *export_path = NULL;
  for (int i = 6; i < argc; i++) {
    if (!strcmp(argv[i], "--writable"))
      writable = 1;
    else if (!strcmp(argv[i], "--export") && i + 1 < argc)
      export_path = argv[++i];
    else
      return 2;
  }
  robotron_disk(m, dac_memory_storage(disk, 819200, writable), writable);
  unsigned long ticks = argc > 4 ? strtoul(argv[4], 0, 0) : 20000000;
  for (unsigned long i = 0; i < ticks; i += 1000)
    robotron_run(m, (unsigned)(ticks - i < 1000 ? ticks - i : 1000));
  if (argc > 5) {
    for (char *p = argv[5]; *p; p++) {
      robotron_key(m, (uint8_t)*p);
      robotron_run(m, *p == 13 || *p == 10 || *p == 26 ? 32000000 : 1000000);
    }
    robotron_run(m, 32000000);
  }
  for (unsigned row = 0; row < 24; row++) {
    for (unsigned col = 0; col < 80; col++) {
      uint8_t c = m->vram[row * 80 + col] & 127;
      putchar(c >= 32 && c < 127 ? c : ' ');
    }
    putchar('\n');
  }
  fprintf(stderr,
          "pc=%04x bank=%02x ticks=%llu reads=%llu writes=%llu video=%llu "
          "fdc=%u dma=%u/%u\n",
          m->cpu.cpu.pc, m->bank, (unsigned long long)m->cpu.cycles,
          (unsigned long long)m->disk_reads, (unsigned long long)m->disk_writes,
          (unsigned long long)m->video_writes, m->fdc.phase, m->dma.enabled,
          m->dma.remaining);
  if (export_path) {
    FILE *f = fopen(export_path, "wbx");
    if (!f) {
      perror(export_path);
      return 2;
    }
    int ok = fwrite(disk, 1, 819200, f) == 819200;
    if (fclose(f) || !ok)
      return 2;
  }
  free(disk);
  free(m);
  return 0;
}
