#include "../../machines/vjuga/vjuga.h"
#include <stdio.h>
#include <stdlib.h>
int main(int argc, char **argv) {
  if (argc < 3) {
    fprintf(stderr, "usage: %s ROM FRAMEBUFFER [decode-mode] [video-writes]\n",
            argv[0]);
    return 2;
  }
  vjuga *m = malloc(sizeof(*m));
  if (!m)
    return 2;
  vjuga_init(m, argc > 3 ? (unsigned)strtoul(argv[3], 0, 0) : 0);
  FILE *f = fopen(argv[1], "rb");
  if (!f) {
    perror(argv[1]);
    free(m);
    return 2;
  }
  size_t n = fread(m->rom, 1, sizeof(m->rom), f);
  int extra = fgetc(f);
  fclose(f);
  if (n != sizeof(m->rom) || extra != EOF) {
    free(m);
    return 2;
  }
  unsigned long target = argc > 4 ? strtoul(argv[4], 0, 0) : 6000;
  while (m->cpu.cycles < 50000000 && m->video_writes < target)
    vjuga_run(m, 1);
  if (m->video_writes != target) {
    fprintf(stderr, "video target not reached pc=%04x writes=%llu\n",
            m->cpu.cpu.pc, (unsigned long long)m->video_writes);
    free(m);
    return 1;
  }
  f = fopen(argv[2], "wb");
  if (!f) {
    free(m);
    return 2;
  }
  int ok = fwrite(m->ram + 0xd800, 1, 40 * 241, f) == 40 * 241;
  fclose(f);
  printf("VJUGA native: mode=%u writes=%llu ticks=%llu\n", m->decode_mode,
         (unsigned long long)m->video_writes,
         (unsigned long long)m->cpu.cycles);
  free(m);
  return ok ? 0 : 1;
}
