/* Decode reference firmware for the released-read data-flow checker. */
#include <stdio.h>
#define CHIPS_UTIL_IMPL
#include "../../../third_party/cpu/chips/z80dasm.h"
static unsigned char rom[2048];
static unsigned at;
static uint8_t input(void *unused) { (void)unused; return rom[(at++) & 2047]; }
static void output(char c, void *unused) { (void)unused; putchar(c); }
int main(int argc, char **argv) {
    if (argc != 2) return 1;
    FILE *f = fopen(argv[1], "rb");
    if (!f || fread(rom, 1, sizeof rom, f) != sizeof rom || fgetc(f) != EOF) return 2;
    fclose(f);
    for (unsigned pc = 0; pc < sizeof rom;) {
        at = pc;
        printf("%04x ", pc);
        pc = z80dasm_op(pc, input, output, NULL);
        putchar('\n');
    }
    return 0;
}
