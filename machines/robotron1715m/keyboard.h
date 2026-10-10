#ifndef DAC_ROBOTRON_KEYBOARD_H
#define DAC_ROBOTRON_KEYBOARD_H
#include "../../common/cpu/z80.h"
/* K7658 reference board: 13 address-selected matrix columns, eight bits each.
 * Clock nominally 683 kHz (RC oscillator), ROM mirrored across memory. */
typedef struct {
  dac_z80 cpu;
  uint8_t rom[2048], matrix[13], leds, last_read;
  unsigned clock_fraction;
  uint64_t strobes;
  uint8_t taps[64], tap_mods[64], synthetic[13];
  unsigned tap_read, tap_count, tap_phase, tap_ticks;
  void *serial_user;
  void (*serial)(void *, unsigned);
} robotron_keyboard;
void robotron_keyboard_init(robotron_keyboard *, const uint8_t *, void *,
                            void (*)(void *, unsigned));
void robotron_keyboard_tick(robotron_keyboard *);
int robotron_keyboard_key(robotron_keyboard *, unsigned column, unsigned bit,
                          int down);
int robotron_keyboard_tap(robotron_keyboard *, unsigned key,
                          unsigned modifiers);
void robotron_keyboard_release(robotron_keyboard *);
void robotron_keyboard_rebind(robotron_keyboard *, void *,
                              void (*)(void *, unsigned));
#endif
