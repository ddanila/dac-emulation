/* Optional libdsk host tool: preserve the captured ID order in a standard DSK.
 * GAP3=0x54 is a reference assumption; TD0 does not record physical gap
 * lengths. No libdsk code is linked into DAC. Refuse unsupported tracks, errors
 * and overwrite. */
#include <libdsk.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
  if (argc != 3) {
    fprintf(stderr, "usage: %s INPUT.TD0 OUTPUT.dsk\n", argv[0]);
    return 2;
  }
  DSK_PDRIVER drive;
  int err = dsk_open(&drive, argv[1], "tele", NULL);
  if (err) {
    fprintf(stderr, "%s\n", dsk_strerror(err));
    return 1;
  }
  DSK_GEOMETRY geometry = {SIDES_ALT, 80,   2,    5, 1, 1024,
                           RATE_SD,   0x1b, 0x54, 0, 0, 0};
  const size_t length = 256 + 160 * 5376;
  unsigned char *image = calloc(1, length);
  if (!image) {
    dsk_close(&drive);
    return 1;
  }
  memcpy(image, "MV - CPCEMU Disk-File\r\nDisk-Info\r\n", 34);
  memcpy(image + 34, "DAC TD0 import", 14);
  image[0x30] = 80;
  image[0x31] = 2;
  image[0x33] = 21;
  for (unsigned c = 0; c < 80; c++)
    for (unsigned h = 0; h < 2; h++) {
      DSK_FORMAT *ids = NULL;
      dsk_psect_t count = 0;
      err = dsk_ptrackids(drive, &geometry, c, h, &count, &ids);
      if (err || count != 5) {
        fprintf(stderr, "Unsupported track %u/%u (%d, %u IDs)\n", c, h, err,
                count);
        dsk_free(ids);
        goto fail;
      }
      unsigned char *track = image + 256 + (c * 2 + h) * 5376;
      memcpy(track, "Track-Info\r\n", 12);
      track[0x10] = c;
      track[0x11] = h;
      track[0x14] = 3;
      track[0x15] = 5;
      track[0x16] = 0x54;
      for (unsigned i = 0; i < 5; i++) {
        DSK_FORMAT *id = &ids[i];
        int deleted = 0;
        if (id->fmt_secsize != 1024 || id->fmt_cylinder > 255 ||
            id->fmt_head > 255 || id->fmt_sector > 255) {
          dsk_free(ids);
          goto fail;
        }
        err = dsk_xread(drive, &geometry, track + 256 + i * 1024, c, h,
                        id->fmt_cylinder, id->fmt_head, id->fmt_sector, 1024,
                        &deleted);
        if (err) {
          fprintf(stderr, "Sector %u/%u/%u: %s\n", c, h, id->fmt_sector,
                  dsk_strerror(err));
          dsk_free(ids);
          goto fail;
        }
        unsigned char *out = track + 0x18 + i * 8;
        out[0] = id->fmt_cylinder;
        out[1] = id->fmt_head;
        out[2] = id->fmt_sector;
        out[3] = 3;
        out[5] = deleted ? 0x40 : 0;
      }
      dsk_free(ids);
    }
  err = dsk_close(&drive);
  if (err && err != DSK_ERR_RDONLY) {
    free(image);
    return 1;
  }
  FILE *f = fopen(argv[2], "wbx");
  if (!f) {
    perror(argv[2]);
    free(image);
    return 1;
  }
  int ok = fwrite(image, 1, length, f) == length;
  if (fclose(f))
    ok = 0;
  free(image);
  return ok ? 0 : 1;
fail:
  dsk_close(&drive);
  free(image);
  return 1;
}
