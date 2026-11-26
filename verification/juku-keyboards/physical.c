/* Independent positions from the matrix/scan inventory, not text mapping calls.
 */
#include "juku_internal.h"
#include <stdio.h>
#include <stdlib.h>
static void run(juku *j, unsigned n) {
  unsigned long end = j->cpu.cyc + n;
  while (j->cpu.cyc < end)
    juku_step(j);
}
int main(int argc, char **argv) {
  if (argc != 3)
    return 2;
  uint8_t rom[16384];
  FILE *f = fopen(argv[1], "rb");
  if (!f || fread(rom, 1, sizeof rom, f) != sizeof rom)
    return 2;
  fclose(f);
  unsigned profile = atoi(argv[2]),
           layout = juku_profile_info(profile)->keyboard;
  unsigned a = layout == 0   ? 45
               : layout == 1 ? 11
                             : 30,
           shift = layout == 2 ? 42 : 128, ctrl = layout == 2 ? 29 : 129;
  unsigned caps = layout == 0   ? 29
                  : layout == 1 ? 3
                                : 58,
           language = layout == 0   ? 114
                      : layout == 1 ? 5
                                    : 70;
  const char *names[] = {
      "a",          "shift-a",      "ctrl-a",       "caps-a",
      "language-a", "up",           "right",        "F1",
      "F8",         "keypad-enter", "numlock-pad1", "right-ctrl-a"};
  unsigned contacts[] = {a,
                         a,
                         a,
                         a,
                         a,
                         layout == 0   ? 82
                         : layout == 1 ? 37
                                       : 328,
                         layout == 0   ? 98
                         : layout == 1 ? 21
                                       : 333,
                         layout == 0   ? 24
                         : layout == 1 ? 0
                                       : 59,
                         layout == 0   ? 112
                         : layout == 1 ? 88
                                       : 66,
                         layout == 0   ? 69
                         : layout == 1 ? 85
                                       : 284,
                         layout == 1 ? 100 : 79,
                         a};
  for (unsigned k = 0; k < 12; k++) {
    if ((k == 10 || k == 11) && layout != 2)
      continue;
    juku *j = juku_create();
    if (!j || juku_load_rom(j, rom, sizeof rom) || juku_set_profile(j, profile))
      return 2;
    j->kbd_enabled = 1;
    run(j, 4000000);
    const uint8_t code[] = {0x31, 0,    0x30, 0xcd, 0xd3, 0xff, 0x32, 0,
                            0x20, 0x3e, 0xd3, 0x32, 1,    0x20, 0x76};
    for (unsigned i = 0; i < sizeof code; i++)
      j->ram[0x100 + i] = code[i];
    const uint8_t enter[] = {0x3e, 1, 0xd3, 6, 0xc3, 0, 1};
    for (unsigned i = 0; i < sizeof enter; i++)
      j->ram[0xc100 + i] = enter[i];
    j->ram[0x2001] = 0;
    j->cpu.pc = 0xc100;
    if (k == 3 || k == 4 || k == 10) {
      unsigned lock = k == 3 ? caps : k == 4 ? language : 69;
      if (juku_keyboard_contact(j, lock, 1))
        return 3;
      run(j, 200000);
      if (juku_keyboard_contact(j, lock, 0))
        return 3;
      run(j, 200000);
    }
    if (k == 1 || k == 2 || k == 11)
      if (juku_keyboard_contact(j, k == 1 ? shift : k == 2 ? ctrl : 285, 1))
        return 3;
    if (juku_keyboard_contact(j, contacts[k], 1))
      return 3;
    unsigned long end = j->cpu.cyc + 600000;
    while (j->ram[0x2001] != 0xd3 && j->cpu.cyc < end)
      juku_step(j);
    printf("%s,%u,%02x\n", names[k], j->ram[0x2001] == 0xd3, j->ram[0x2000]);
    juku_destroy(j);
  }
}
