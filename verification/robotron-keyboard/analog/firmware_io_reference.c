#include "../../../machines/robotron1715m/keyboard.h"
#include <stdio.h>

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
    /* Service reset releases at 1 ms; contact 61 closes at 5 ms.
     * Compare ordinal bits, not cycle equivalence between CPU models. */
    for (cycle = 0; cycle < 29000; cycle++) {
        if (cycle == 4000) robotron_keyboard_key(&keyboard, 7, 5, 1);
        dac_z80_tick(&keyboard.cpu, 0, 0);
    }
    return 0;
}
