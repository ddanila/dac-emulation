/* Hardware decoded from Zander's 56-330-4103-7 schematic; cross-checked
 * against MAME rt1715.cpp (BSD-3-Clause; see REFERENCE_LICENSE). */
#include "keyboard.h"
#include <errno.h>
#include <string.h>
static uint8_t read_rom(void *p, uint16_t a) {
  return ((robotron_keyboard *)p)->rom[a & 2047];
}
static void no_write(void *p, uint16_t a, uint8_t v) {
  (void)p;
  (void)a;
  (void)v;
}
static uint8_t input(void *p, uint16_t a) {
  robotron_keyboard *k = p;
  /* The shared CPU presents a bus access over multiple clock ticks. The
   * external flip-flops toggle once per I/O strobe, not once per tick. */
  if ((k->cpu.pins & (Z80_IORQ | Z80_RD)) == (Z80_IORQ | Z80_RD))
    return k->last_read;
  uint8_t v = 0xff;
  if ((a & 0x7fff) == 0x2000)
    k->leds ^= 1;
  else if ((a & 0x7fff) == 0x4000)
    k->leds ^= 2;
  else if ((a & 0xe000) == 0x8000)
    for (unsigned i = 0; i < 13; i++)
      if (a & (1u << i))
        v &= k->matrix[i] | k->synthetic[i];
  return k->last_read = v;
}
static void output(void *p, uint16_t a, uint8_t v) {
  robotron_keyboard *k = p;
  if (a >= 0x2000 || (k->cpu.pins & (Z80_IORQ | Z80_WR)) == (Z80_IORQ | Z80_WR))
    return;
  k->strobes++;
  if (k->serial)
    k->serial(k->serial_user, v & 1);
}
void robotron_keyboard_init(robotron_keyboard *k, const uint8_t *rom,
                            void *user, void (*serial)(void *, unsigned)) {
  memset(k, 0, sizeof(*k));
  memcpy(k->rom, rom, sizeof(k->rom));
  k->serial_user = user;
  k->serial = serial;
  dac_z80_init(&k->cpu,
               (dac_z80_bus){k, read_rom, no_write, input, output, NULL});
}
void robotron_keyboard_tick(robotron_keyboard *k) {
  if (k->tap_ticks)
    k->tap_ticks--;
  else if (k->tap_phase == 1) {
    memset(k->synthetic, 0, sizeof(k->synthetic));
    k->tap_phase = 2;
    k->tap_ticks = 160000;
  } else if (k->tap_count) {
    unsigned key = k->taps[k->tap_read], mods = k->tap_mods[k->tap_read];
    k->tap_read = (k->tap_read + 1) % 64;
    k->tap_count--;
    k->synthetic[key / 8] |= 1u << (key % 8);
    if (mods & 1)
      k->synthetic[8] |= 2;
    if (mods & 2)
      k->synthetic[8] |= 1;
    k->tap_phase = 1;
    k->tap_ticks = 240000;
  } else
    k->tap_phase = 0;
  k->clock_fraction += 683000;
  if (k->clock_fraction >= 3993600) {
    k->clock_fraction -= 3993600;
    dac_z80_tick(&k->cpu, 0, 0);
  }
}
int robotron_keyboard_key(robotron_keyboard *k, unsigned col, unsigned bit,
                          int down) {
  if (col >= 13 || bit >= 8)
    return -EINVAL;
  if (down)
    k->matrix[col] |= 1u << bit;
  else
    k->matrix[col] &= ~(1u << bit);
  return 0;
}

int robotron_keyboard_tap(robotron_keyboard *k, unsigned key,
                          unsigned modifiers) {
  if (key >= 104 || modifiers > 3)
    return -EINVAL;
  if (k->tap_count == 64)
    return -ENOSPC;
  unsigned pos = (k->tap_read + k->tap_count++) % 64;
  k->taps[pos] = key;
  k->tap_mods[pos] = modifiers;
  return 0;
}
void robotron_keyboard_release(robotron_keyboard *k) {
  memset(k->matrix, 0, sizeof(k->matrix));
  memset(k->synthetic, 0, sizeof(k->synthetic));
  k->tap_read = k->tap_count = k->tap_phase = k->tap_ticks = 0;
}

void robotron_keyboard_rebind(robotron_keyboard *k, void *user,
                              void (*serial)(void *, unsigned)) {
  k->cpu.bus = (dac_z80_bus){k, read_rom, no_write, input, output, NULL};
  k->serial_user = user;
  k->serial = serial;
}
