#include "../../../machines/robotron1715m/keyboard.h"
#include <stdio.h>
#include "io_scenario.h"

static unsigned cycle;
static void bit(void *user, unsigned value) {
    (void)user;
    printf("BIT %u %u\n", cycle, value);
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    unsigned char rom[2048];
    FILE *file = fopen(argv[1], "rb");
    if (!file) return 2;
    size_t count = fread(rom, 1, sizeof rom, file);
    int extra = fgetc(file);
    fclose(file);
    if (count != sizeof rom || extra != EOF) return 2;
    robotron_keyboard keyboard;
    robotron_keyboard_init(&keyboard, rom, NULL, bit);
    unsigned contact = 0, reset = 0, reset_asserted = 0;
    unsigned char closed[104] = {0};
#ifdef OBSERVE_LEDS
    unsigned previous_leds = keyboard.leds;
    printf("LED %u %u\n", 0u, previous_leds);
#endif
    /* Compare ordinal bits, not cycle equivalence between CPU models. */
    for (cycle = 0; cycle < SCENARIO_CYCLES; cycle++) {
        while (contact_events[contact].cycle == cycle) {
            unsigned index = contact_events[contact].index;
            closed[index] = (unsigned char)contact_events[contact].closed;
            robotron_keyboard_key(&keyboard, index / 8, index % 8, closed[index]);
            contact++;
        }
        while (reset_events[reset].cycle == cycle) {
            reset_asserted = reset_events[reset++].asserted;
            if (reset_asserted) {
                robotron_keyboard_init(&keyboard, rom, NULL, bit);
                /* Reset does not physically open held contacts. */
                for (unsigned index = 0; index < 104; index++)
                    if (closed[index]) robotron_keyboard_key(&keyboard, index / 8, index % 8, 1);
            }
        }
        if (!reset_asserted) dac_z80_tick(&keyboard.cpu, 0, 0);
#ifdef OBSERVE_LEDS
        if (keyboard.leds != previous_leds) {
            printf("LED %u %u\n", cycle, keyboard.leds);
            previous_leds = keyboard.leds;
        }
#endif
    }
    return 0;
}
