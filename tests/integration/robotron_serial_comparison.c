/* Original S600 serial observations for optional MAME differential tests. */
#include "../../machines/robotron1715m/robotron.h"
#include <stdio.h>
static robotron m;
static void reg(unsigned index, unsigned value) {
  robotron_output(&m, 14, index);
  robotron_output(&m, 14, value);
}
static void drain(unsigned test) {
  unsigned count = 0;
  while ((robotron_input(&m, 14) & 1) && count++ < 8) {
    robotron_output(&m, 14, 1);
    unsigned status = robotron_input(&m, 14);
    unsigned data = robotron_input(&m, 12);
    printf("RX %u %02x %02x\n", test, data, status & 0x70);
  }
}
int main(int argc, char **argv) {
  if (argc != 2) return 2;
  unsigned char rom[2048];
  FILE *file = fopen(argv[1], "rb");
  if (!file || fread(rom, 1, sizeof(rom), file) != sizeof(rom) || fgetc(file) != EOF) return 2;
  fclose(file);
  robotron_init(&m);
  m.rom[0] = 0x76;
  robotron_keyboard_load(&m, rom, sizeof(rom));
  robotron_run(&m, 4000000);
  for (unsigned test = 0; test < 3; test++) {
    robotron_output(&m, 14, 0x18);
    reg(3, test == 1 ? 0x41 : 0xc1); /* 7 or 8 data bits. */
    reg(4, test == 1 ? 7 : 4);       /* Deliberately mismatch 7E1 against S600 8N1. */
    robotron_keyboard_key(&m.keyboard, 7, 5, 1); /* A */
    robotron_run(&m, 400000);
    robotron_keyboard_key(&m.keyboard, 7, 5, 0);
    robotron_run(&m, 400000);
    if (test == 2) {
      robotron_keyboard_key(&m.keyboard, 7, 5, 1);
      robotron_run(&m, 400000);
      robotron_keyboard_key(&m.keyboard, 7, 5, 0);
      robotron_run(&m, 400000);
    }
    drain(test);
  }
  return 0;
}
