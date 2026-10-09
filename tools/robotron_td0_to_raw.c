/* Optional host utility: compile with libdsk, never linked into the emulator.
 * Decodes every physical sector; refuses errors and existing output files. */
#include <stddef.h>
#include <stdio.h>

/* libdsk.h requires size_t to be declared by its caller. */
#include <libdsk.h>
int main(int argc, char **argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: %s INPUT.TD0 OUTPUT.img\n", argv[0]);
    return 2;
  }
  DSK_PDRIVER drive;
  int err = dsk_open(&drive, argv[1], "tele", NULL);
  if (err) {
    fprintf(stderr, "TeleDisk open: %s\n", dsk_strerror(err));
    return 1;
  }
  DSK_GEOMETRY geometry = {SIDES_ALT, 80,   2,    5, 1, 1024,
                           RATE_SD,   0x1b, 0x54, 0, 0, 0};
  unsigned char data[819200];
  unsigned pos = 0;
  for (unsigned c = 0; c < 80; c++)
    for (unsigned h = 0; h < 2; h++)
      for (unsigned s = 1; s <= 5; s++, pos += 1024) {
        err = dsk_pread(drive, &geometry, data + pos, c, h, s);
        if (err) {
          fprintf(stderr, "sector %u/%u/%u: %s\n", c, h, s, dsk_strerror(err));
          dsk_close(&drive);
          return 1;
        }
      }
  err = dsk_close(&drive);
  /* libdsk may report read-only when closing compressed TeleDisk input.
   * Every sector was read successfully; this utility never requests a write. */
  if (err && err != DSK_ERR_RDONLY) {
    fprintf(stderr, "TeleDisk close: %s (%d)\n", dsk_strerror(err), err);
    return 1;
  }
  FILE *out = fopen(argv[2], "wbx");
  if (!out) {
    perror(argv[2]);
    return 1;
  }
  int ok = fwrite(data, 1, sizeof(data), out) == sizeof(data);
  if (fclose(out) || !ok)
    return 1;
  return 0;
}
