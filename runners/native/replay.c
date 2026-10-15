/* DACR1/2 are bounded, little-endian transports for DAC-recording-1/2.
 * The museum's replay-native.mjs validates its JSON envelope and converts it.
 * Output: length-prefixed video, disk A, disk B, printer; DACR2 adds V.24.
 */
#include "../../common/runtime/session.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void fail(void) {
  fputs("Invalid replay or rejected event\n", stderr);
  exit(2);
}
static uint32_t number(void) {
  uint8_t b[4];
  if (fread(b, 1, 4, stdin) != 4)
    fail();
  return (uint32_t)b[0] | (uint32_t)b[1] << 8 | (uint32_t)b[2] << 16 |
         (uint32_t)b[3] << 24;
}
static void *bytes(uint32_t n) {
  if (n > 1638400)
    fail();
  void *p = malloc(n ? n : 1);
  if (!p || fread(p, 1, n, stdin) != n)
    fail();
  return p;
}
static void output(const void *p, uint32_t n) {
  uint8_t b[4] = {n, n >> 8, n >> 16, n >> 24};
  if (fwrite(b, 1, 4, stdout) != 4 || (n && fwrite(p, 1, n, stdout) != n))
    fail();
}
int main(void) {
  char magic[5];
  if (fread(magic, 1, 5, stdin) != 5 ||
      (memcmp(magic, "DACR1", 5) && memcmp(magic, "DACR2", 5)))
    fail();
  dac_session *s = dac_create(number());
  if (!s)
    fail();
  unsigned count = number();
  if (count > 4)
    fail();
  while (count--) {
    unsigned slot = number(), n = number();
    void *p = bytes(n);
    if (dac_load(s, slot, p, n) < 0)
      fail();
    free(p);
  }
  for (unsigned u = 0; u < 2; u++) {
    unsigned writable = number(), n = number();
    void *p = bytes(n);
    if (writable > 1 || (n && dac_mount_unit(s, u, p, n, writable) < 0))
      fail();
    free(p);
  }
  if (dac_power(s, 1) < 0)
    fail();
  unsigned media_count = number();
  if (media_count > 8)
    fail();
  void *media[8] = {0};
  unsigned media_size[8], protection[8];
  for (unsigned i = 0; i < media_count; i++) {
    protection[i] = number();
    if (protection[i] > 1)
      fail();
    media_size[i] = number();
    media[i] = bytes(media_size[i]);
  }
  count = number();
  if (count > 100000)
    fail();
  while (count--) {
    unsigned op = number(), a = number(), b = number();
    int r = -1;
    if (op == 0 && a && a <= 100000)
      r = dac_run(s, a) ? 0 : -1;
    else if (op == 1 && a <= 255 && b <= 1)
      r = dac_key(s, a, b);
    else if (op == 2 && a < 104 && b <= 1)
      r = dac_matrix(s, a, b);
    else if (op == 3 && a < 104 && b <= 3)
      r = dac_tap(s, a, b);
    else if (op == 7 && a < 2 && b < media_count)
      r = dac_mount_unit(s, a, media[b], media_size[b], protection[b]);
    else if (op == 17)
      r = dac_serial_peer(s, a, b);
    else if (op == 18) {
      dac_serial_cancel(s);
      r = 0;
    } else if (op == 13 && a < 256)
      r = dac_serial_send(s, a);
    else if (op == 14 && a < 8)
      r = dac_serial_signals(s, a);
    else if (op == 15) {
      dac_serial_clear(s);
      r = 0;
    } else if (op == 16 && a < 4)
      r = dac_cables(s, a);
    else if (op == 12 && a < 2 && b < 2)
      r = dac_drive_protect(s, a, b);
    else if (op == 11 && a < 2 && b < 2)
      r = dac_drive_transfer(s, a, b);
    else if (op == 10 && a < 2 && b < 2)
      r = dac_drive_inserted(s, a, b);
    else if (op == 9 && a < 2 && b < 2)
      r = dac_drive_door(s, a, b);
    else if (op == 8) {
      dac_printer_clear(s);
      r = 0;
    } else if (op == 4)
      r = dac_reset(s);
    else if (op == 5 || op == 6)
      r = dac_power(s, op == 6);
    if (r < 0)
      fail();
  }
  if (fgetc(stdin) != EOF)
    fail();
  const void *video = dac_video(s);
  output(video, dac_width(s) * dac_height(s) * 4);
  for (unsigned u = 0; u < 2; u++)
    output(dac_disk_data_unit(s, u), dac_disk_size_unit(s, u));
  output(dac_printer_data(s), dac_printer_size(s));
  if (magic[4] == '2')
    output(dac_serial_data(s), dac_serial_size(s));
  for (unsigned i = 0; i < media_count; i++)
    free(media[i]);
  dac_destroy(s);
  return 0;
}
