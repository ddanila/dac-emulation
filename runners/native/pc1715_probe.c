/* Headless ROM/controller bring-up probe. A successful run is NOT a disk boot. */
#include "../../machines/robotron1715/pc1715.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static FILE *trace_file;
static uint64_t reads[256], writes[256];
static void capture(void *user, const dac_trace_event *e) {
  (void)user;
  if (!strcmp(e->kind, "IR")) reads[e->address & 255]++;
  else if (!strcmp(e->kind, "IW")) writes[e->address & 255]++;
  else return;
  if (trace_file)
    fprintf(trace_file, "%" PRIu64 " %s %04x %02x\n", e->cycle,
            e->kind, (unsigned)e->address, e->data);
}
int main(int argc, char **argv) {
  if (argc < 2 || argc > 4) {
    fprintf(stderr, "usage: %s ROM [ticks=10000000] [new-trace-file]\n", argv[0]);
    return 2;
  }
  uint64_t ticks = 10000000;
  if (argc > 2) {
    char *end;
    errno = 0;
    ticks = strtoull(argv[2], &end, 10);
    if (errno || !*argv[2] || *end || !ticks || ticks > 500000000) return 2;
  }
  pc1715 *m = malloc(sizeof(*m));
  if (!m) return 2;
  pc1715_init(m);
  FILE *f = fopen(argv[1], "rb");
  int loaded = f && fread(m->rom, 1, sizeof(m->rom), f) == sizeof(m->rom) &&
               fgetc(f) == EOF && !ferror(f);
  if (f) fclose(f);
  if (!loaded) { free(m); fputs("Expected a 2048-byte ROM\n", stderr); return 2; }
  if (argc > 3) {
    trace_file = fopen(argv[3], "wx");
    if (!trace_file) { perror("trace"); free(m); return 2; }
  }
  m->trace = (dac_trace_sink){capture, NULL, 0, 0};
  for (uint64_t i = 0; i < ticks;) {
    unsigned n = ticks - i > 10000 ? 10000 : (unsigned)(ticks - i);
    pc1715_run(m, n);
    i += n;
  }
  printf("{\"profile\":\"pc1715-headless-no-controller\",\"clock_hz\":%u,"
         "\"cycles\":%" PRIu64 ",\"pc\":%u,\"rom_enabled\":%u,"
         "\"io_reads\":%" PRIu64 ",\"io_writes\":%" PRIu64 ","
         "\"unclaimed_reads\":%" PRIu64 ",\"disk_boot_supported\":false,\"ports\":[",
         PC1715_CLOCK_HZ, m->cpu.cycles, m->cpu.cpu.pc, m->rom_enabled,
         m->io_reads, m->io_writes, m->unclaimed_reads);
  int comma = 0;
  for (unsigned i = 0; i < 256; i++)
    if (reads[i] || writes[i]) {
      printf("%s{\"port\":%u,\"reads\":%" PRIu64 ",\"writes\":%" PRIu64 "}",
             comma ? "," : "", i, reads[i], writes[i]);
      comma = 1;
    }
  puts("]}");
  int failed = ferror(stdout);
  if (trace_file && fclose(trace_file)) failed = 1;
  free(m);
  return failed ? 1 : 0;
}
