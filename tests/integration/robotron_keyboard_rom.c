/* Optional historical-ROM test. Supply S600 externally; no ROM in this repo. */
#include "../../machines/robotron1715m/robotron.h"
#include <assert.h>
#include <stdio.h>
static robotron m;
static unsigned count;
static uint8_t received[256];
static void run(unsigned ticks) {
  while (ticks) {
    unsigned n = ticks > 1000 ? 1000 : ticks;
    robotron_run(&m, n);
    ticks -= n;
    while (m.rx.count) {
      assert(count < 256);
      received[count++] = robotron_sio_read(&m, 0);
    }
  }
}
static void press(unsigned col, unsigned bit) {
  robotron_keyboard_key(&m.keyboard, col, bit, 1);
  run(400000);
  robotron_keyboard_key(&m.keyboard, col, bit, 0);
  run(400000);
}
int main(int argc, char **argv) {
  if (argc != 2) {
    fprintf(stderr, "usage: keyboard-rom-test S600.bin\n");
    return 2;
  }
  uint8_t rom[2048];
  FILE *f = fopen(argv[1], "rb");
  assert(f && fread(rom, 1, sizeof(rom), f) == sizeof(rom) && fgetc(f) == EOF);
  fclose(f);
  robotron_init(&m);
  m.rom[0] = 0x76;
  assert(!robotron_keyboard_load(&m, rom, sizeof(rom)));
  m.sio_regs[0][3] = 0xc1;
  m.sio_regs[0][4] = 4;
  run(1000000);
  count = 0;
  press(7, 5);
  assert(count == 2 && received[0] == 0xe0 && received[1] == 'a');
  count = 0;
  robotron_keyboard_key(&m.keyboard, 8, 1, 1);
  run(400000);
  press(7, 5);
  assert(count == 2 && received[1] == 'A');
  robotron_keyboard_release(&m.keyboard);
  run(400000);
  count = 0;
  robotron_keyboard_key(&m.keyboard, 8, 0, 1);
  run(400000);
  press(7, 5);
  assert(count == 2 && received[0] == 0xe1 && received[1] == 'a');
  robotron_keyboard_release(&m.keyboard);
  run(400000);
  count = 0;
  press(3, 4);
  assert(count == 2 && received[1] == 0x9e);
  count = 0;
  press(8, 7);
  assert(m.keyboard.leds & 1);
  assert(!m.rx.errors);
  puts("PASS S600: matrix A, Shift+A, Ctrl+A, ET, SI/SO LED and clocked 8N1 "
       "receiver");
}
