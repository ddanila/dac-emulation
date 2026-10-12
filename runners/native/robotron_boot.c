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
static uint8_t *load_disk(const char *path, size_t *size) {
  FILE *f = fopen(path, "rb");
  if (!f)
    return NULL;
  if (fseek(f, 0, SEEK_END)) {
    fclose(f);
    return NULL;
  }
  long n = ftell(f);
  if (n < 256 || n > 1048576 || fseek(f, 0, SEEK_SET)) {
    fclose(f);
    return NULL;
  }
  uint8_t *data = malloc((size_t)n);
  if (!data || fread(data, 1, (size_t)n, f) != (size_t)n) {
    free(data);
    fclose(f);
    return NULL;
  }
  fclose(f);
  *size = (size_t)n;
  return data;
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
  size_t disk_size = 0, disk_b_size = 0;
  uint8_t *disk = load_disk(argv[3], &disk_size);
  if (!m || !disk)
    return 2;
  robotron_init(m);
  if (getenv("DAC_TRACE_IO"))
    m->trace = (dac_trace_sink){trace, 0, 0, 0};
  if (!load(argv[1], m->rom, 2048) || !load(argv[2], m->prom, 256))
    return 2;
  int writable = 0;
  const char *export_path = NULL, *b_path = NULL, *export_b = NULL,
             *printer_path = NULL;
  int writable_b = 0;
  unsigned settle = 32000000;
  uint8_t *disk_b = NULL;
  for (int i = 6; i < argc; i++) {
    if (!strcmp(argv[i], "--writable"))
      writable = 1;
    else if (!strcmp(argv[i], "--export") && i + 1 < argc)
      export_path = argv[++i];
    else if (!strcmp(argv[i], "--disk-b") && i + 1 < argc)
      b_path = argv[++i];
    else if (!strcmp(argv[i], "--export-b") && i + 1 < argc)
      export_b = argv[++i];
    else if (!strcmp(argv[i], "--printer") && i + 1 < argc)
      printer_path = argv[++i];
    else if (!strcmp(argv[i], "--settle") && i + 1 < argc)
      settle = (unsigned)strtoul(argv[++i], 0, 0);
    else if (!strcmp(argv[i], "--writable-b"))
      writable_b = 1;
    else
      return 2;
  }
  if (b_path) {
    disk_b = load_disk(b_path, &disk_b_size);
    if (!disk_b)
      return 2;
    if (robotron_disk_unit(m, 1,
                           dac_memory_storage(disk_b, disk_b_size, writable_b),
                           writable_b))
      return 2;
  }
  if (robotron_disk(m, dac_memory_storage(disk, disk_size, writable), writable))
    return 2;
  unsigned long ticks = argc > 4 ? strtoul(argv[4], 0, 0) : 20000000;
  for (unsigned long i = 0; i < ticks; i += 1000)
    robotron_run(m, (unsigned)(ticks - i < 1000 ? ticks - i : 1000));
  if (argc > 5) {
    for (char *p = argv[5]; *p; p++) {
      robotron_key(m, (uint8_t)*p);
      robotron_run(m, *p == 13 || *p == 10 || *p == 26 ? settle : 1000000);
    }
    robotron_run(m, settle);
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
    int ok = fwrite(disk, 1, disk_size, f) == disk_size;
    if (fclose(f) || !ok)
      return 2;
  }
  if (export_b) {
    FILE *f = fopen(export_b, "wbx");
    if (!f || !disk_b)
      return 2;
    int ok = fwrite(disk_b, 1, disk_b_size, f) == disk_b_size;
    if (fclose(f) || !ok)
      return 2;
  }
  if (printer_path) {
    FILE *f = fopen(printer_path, "wbx");
    if (!f)
      return 2;
    int ok = fwrite(m->printer, 1, m->printer_size, f) == m->printer_size;
    if (fclose(f) || !ok)
      return 2;
  }
  free(disk_b);
  free(disk);
  free(m);
  return 0;
}
