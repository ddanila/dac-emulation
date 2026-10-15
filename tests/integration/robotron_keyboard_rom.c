/* Optional historical-ROM test. Supply S600 externally; no ROM in this repo. */
#include "../../machines/robotron1715m/robotron.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
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
static void start(const uint8_t *rom) {
  robotron_init(&m);
  m.rom[0] = 0x76;
  assert(!robotron_keyboard_load(&m, rom, 2048));
  m.sio_regs[0][3] = 0xc1;
  m.sio_regs[0][4] = 4;
  count = 0;
  run(1000000);
  count = 0;
}
static void audit(const uint8_t *rom) {
  puts("{\"profile\":\"S600 reference; observed packets, not specimen legend "
       "qualification\",\"cases\":[");
  for (unsigned mods = 0; mods < 4; mods++)
    for (unsigned key = 0; key < 104; key++) {
      start(rom);
      if (mods & 1)
        robotron_keyboard_key(&m.keyboard, 8, 1, 1);
      if (mods & 2)
        robotron_keyboard_key(&m.keyboard, 8, 0, 1);
      run(400000);
      count = 0;
      press(key / 8, key % 8);
      assert(!m.rx.errors);
      printf("%s{\"key\":%u,\"modifiers\":%u,\"leds\":%u,\"packet\":[",
             mods || key ? ",\n" : "", key, mods, m.keyboard.leds);
      for (unsigned i = 0; i < count; i++)
        printf("%s%u", i ? "," : "", received[i]);
      printf("]}");
      robotron_keyboard_release(&m.keyboard);
      run(400000);
      /* Physical release empties the contact matrix even when firmware modes
       * latch. */
      for (unsigned i = 0; i < 13; i++)
        assert(m.keyboard.matrix[i] == 0);
    }
  puts("\n]}");
}
int main(int argc, char **argv) {
  if (argc != 2 && argc != 3) {
    fprintf(stderr, "usage: keyboard-rom-test S600.bin\n");
    return 2;
  }
  uint8_t rom[2048];
  FILE *f = fopen(argv[1], "rb");
  assert(f && fread(rom, 1, sizeof(rom), f) == sizeof(rom) && fgetc(f) == EOF);
  fclose(f);
  if (argc == 3) {
    assert(!strcmp(argv[2], "--audit"));
    audit(rom);
    return 0;
  }
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
  press(7, 5); /* released Shift must not leave the firmware shifted */
  assert(count == 2 && received[1] == 'a');
  count = 0;
  robotron_keyboard_key(&m.keyboard, 8, 0, 1);
  run(400000);
  press(7, 5);
  assert(count == 2 && received[0] == 0xe1 && received[1] == 'a');
  robotron_keyboard_release(&m.keyboard);
  run(400000);
  count = 0;
  press(7, 5); /* released Ctrl must restore the normal serial prefix */
  assert(count == 2 && received[0] == 0xe0 && received[1] == 'a');
  count = 0;
  press(3, 4);
  assert(count == 2 && received[1] == 0x9e);
  count = 0;
  press(8, 7);
  assert(m.keyboard.leds == 1);
  for (unsigned i = 0; i < 100; i++) {
    run(4000);
    assert(m.keyboard.leds == 1);
  }
  press(8, 5);
  assert(m.keyboard.leds == 3);
  for (unsigned i = 0; i < 100; i++) {
    run(4000);
    assert(m.keyboard.leds == 3);
  }
  press(8, 7);
  assert(m.keyboard.leds == 2);
  press(8, 5);
  assert(m.keyboard.leds == 0);
  start(rom);
  robotron_keyboard_key(&m.keyboard, 7, 5, 1);
  run(8000000);
  assert(count >= 2 && !(count % 2));
  for (unsigned i = 0; i < count; i += 2)
    assert(received[i] == 0xe0 && received[i + 1] == 'a');
  unsigned held_packets = count / 2;
  robotron_keyboard_key(&m.keyboard, 2, 5, 1);
  run(400000);
  robotron_keyboard_release(&m.keyboard);
  run(400000);
  count = 0;
  press(7, 5);
  assert(count == 2 && received[1] == 'a');
  fprintf(stderr,
          "S600 held A: %u packets in two emulated seconds; two-key overlap "
          "releases cleanly\n",
          held_packets);
  start(rom);
  press(7, 5);
  count = 0;
  robotron_keyboard_key(&m.keyboard, 8, 6, 1);
  run(8000000);
  assert(count ==
         0); /* REP repeats a held contact, not the last released key. */
  robotron_keyboard_release(&m.keyboard);
  run(400000);
  count = 0;
  robotron_keyboard_key(&m.keyboard, 7, 5, 1);
  run(400000);
  count = 0;
  robotron_keyboard_key(&m.keyboard, 8, 6, 1);
  run(8000000);
  assert(count >= 4 && !(count % 2));
  for (unsigned i = 0; i < count; i += 2)
    assert(received[i] == 0xe0 && received[i + 1] == 'a');
  robotron_keyboard_key(&m.keyboard, 8, 6, 0);
  run(400000);
  count = 0;
  run(4000000);
  assert(!count); /* Releasing REP stops repetition while A stays held. */
  robotron_keyboard_release(&m.keyboard);
  run(400000);
  count = 0;
  press(2, 5);
  assert(count == 2 && received[1] == 's');
  start(rom);
  robotron_keyboard_key(&m.keyboard, 8, 1, 1);
  run(400000);
  robotron_keyboard_key(&m.keyboard, 8, 0, 1);
  run(400000);
  count = 0;
  press(7, 5);
  assert(count == 2 && received[0] == 0xe3 && received[1] == 'A');
  robotron_keyboard_key(&m.keyboard, 8, 1, 0);
  run(400000);
  count = 0;
  press(7, 5);
  assert(count == 2 && received[0] == 0xe1 && received[1] == 'a');
  robotron_keyboard_release(&m.keyboard);
  run(400000);
  count = 0;
  press(7, 5);
  assert(count == 2 && received[0] == 0xe0 && received[1] == 'a');
  assert(!m.rx.errors);
  /* Removing keyboard power stops its CPU without stopping the host. */
  m.disconnected = 1;
  uint64_t keyboard_cycles = m.keyboard.cpu.cycles, host_cycles = m.cpu.cycles;
  run(400000);
  assert(m.keyboard.cpu.cycles == keyboard_cycles &&
         m.cpu.cycles > host_cycles);
  m.disconnected = 0;
  run(400000);
  assert(m.keyboard.cpu.cycles > keyboard_cycles);
  puts("PASS S600: matrix A, Shift+A, Ctrl+A, ET, stable Caps/SI/SO LEDs and "
       "clocked 8N1 "
       "receiver");
}
