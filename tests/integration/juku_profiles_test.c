#include "../../common/runtime/observe.h"
#include "../../machines/juku/juku_internal.h"
#include <assert.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static void input(juku *j, uint8_t key, unsigned col, unsigned row,
                  unsigned shift) {
  juku_key(j, key, 1);
  j->kbd_col = col;
  uint8_t v = j->cpu.port_in(j, 5);
  assert((v & 15) == ((~row & 7) << 1));
  assert((!(v & 64)) == shift);
  juku_key(j, 0, 0);
  assert((j->cpu.port_in(j, 5) & 15) == 15);
}
static void profiles_test(void) {
  for (unsigned id = 0; id < JUKU_PROFILE_COUNT; id++) {
    juku *j = juku_create();
    assert(j && !juku_set_profile(j, id));
    unsigned base = juku_profile_info(id)->card ? 0x30 : 0x1c;
    j->fdc_enabled = 1;
    j->cpu.port_out(j, (uint8_t)(base + 1), j->fdc_bus_invert ? 248 : 7);
    assert(j->fdc.track == 7);
    j->cpu.port_out(j, (uint8_t)((base == 0x30 ? 0x1c : 0x30) + 1), 99);
    assert(j->fdc.track == 7);
    if (id == 1 || id == 2 || id == 6) {
      input(j, 'T', 5, 2, 1);
      input(j, 'd', 3, 3, 0);
      input(j, 13, 13, 3, 0);
      input(j, '?', 9, 4, 1);
    }
    if (id == 5) {
      // Disk firmware also touches PA5 while no key is pending.
      for (unsigned i = 0; i < 3; i++) {
        j->cpu.port_out(j, 4, 32);
        j->cpu.port_out(j, 4, 0);
      }
      juku_key(j, 'f', 1);
      assert(j->cpu.port_in(j, 5) & 128);
      unsigned scan = 0;
      for (unsigned bit = 0; bit < 8; bit++) {
        scan |= (j->cpu.port_in(j, 5) & 1) << bit;
        j->cpu.port_out(j, 4, 32);
        j->cpu.port_out(j, 4, 0);
      }
      assert(scan == 0x21);
      j->cpu.port_out(j, 4, 128);
      j->cpu.port_out(j, 4, 0);
      assert(!(j->cpu.port_in(j, 5) & 128));
      juku_key(j, 0, 0);
      assert(j->at_queue[0] == 0xa1);
    }
    juku_destroy(j);
    dac_session *s = dac_create(0);
    uint8_t rom[16384] = {0xc3, 0, 0};
    assert(!dac_juku_set_profile(s, id));
    assert(!dac_load(s, 0, rom, sizeof(rom)));
    assert(!dac_power(s, 1));
    assert(dac_juku_set_profile(s, 0) == -EBUSY);
    dac_run(s, 1000);
    size_t n = dac_state_size(s);
    void *state = malloc(n);
    assert(!dac_state_save(s, state, n));
    assert(!dac_reset(s));
    assert(dac_juku_get_profile(s) == id);
    assert(!dac_state_load(s, state, n));
    assert(!dac_power(s, 0));
    assert(!dac_juku_set_profile(s, (id + 1) % JUKU_PROFILE_COUNT));
    assert(dac_state_load(s, state, n) < 0);
    assert(!dac_juku_set_profile(s, id));
    assert(!dac_power(s, 1));
    assert(dac_juku_get_profile(s) == id);
    free(state);
    dac_destroy(s);
  }
}
static void track_write(wd179x *f, unsigned *n, uint8_t b) {
  wd179x_write(f, 3, b);
  *n += b == 0xf7 ? 2 : 1;
}
static void media_test(void) {
  /* Compressed FM image, deliberately nonsequential IDs. */
  uint8_t image[] = {'I', 'M', 'D', ' ', 't', 0x1a, 2, 0,   0,
                     2,   0,   3,   1,   2,   0x5a, 8, 0xa5};
  dac_session *session = dac_create(0);
  uint8_t rom[16384] = {0};
  const uint8_t boot[] = {0xf3, 0x3e, 4,    0xd3, 6,    0x3e, 0xfc,
                          0xd3, 0x1e, 0x3e, 0x7f, 0xd3, 0x1c, 0x21,
                          0,    0x80, 6,    128,  0xdb, 0x1f, 0x2f,
                          0x77, 0x23, 5,    0xc2, 18,   0,    0x76};
  memcpy(rom, boot, sizeof(boot));
  assert(!dac_juku_set_profile(session, 6));
  assert(!dac_load(session, 0, rom, sizeof(rom)));
  assert(!dac_mount(session, image, sizeof(image), 1));
  assert(!dac_power(session, 1));
  dac_run(session, 100000);
  uint8_t loaded[128];
  assert(!dac_peek(session, DAC_MEMORY_RAM, 0x8000, loaded, sizeof(loaded)));
  for (unsigned i = 0; i < 128; i++)
    assert(loaded[i] == 0x5a);
  size_t saved_size = dac_state_size(session);
  void *saved = malloc(saved_size);
  assert(!dac_state_save(session, saved, saved_size));
  assert(!dac_reset(session));
  assert(!dac_state_load(session, saved, saved_size));
  assert(!dac_peek(session, DAC_MEMORY_RAM, 0x8000, loaded, sizeof(loaded)));
  assert(dac_juku_get_profile(session) == 6 && loaded[127] == 0x5a);
  free(saved);
  dac_destroy(session);
  uint8_t *raw = NULL;
  size_t n = 0;
  assert(!wd_disk_import(image, sizeof(image), &raw, &n));
  wd_disk *d = calloc(1, sizeof(*d));
  assert(!wd_disk_bind_image(d, dac_memory_storage(raw, n, 1), 1));
  assert(wd_disk_sector_id(d, 0, 0, 0) == 3 &&
         wd_disk_sector_size(d, 0, 0, 3) == 128);
  assert(wd_disk_sector_deleted(d, 0, 0, 1) == 1 &&
         wd_disk_sector_error(d, 0, 0, 1));
  wd179x f;
  wd179x_init(&f, d);
  f.fm_only = 1;
  wd179x_portc(&f, 4);
  wd179x_write(&f, 2, 3);
  wd179x_write(&f, 0, 0x80);
  for (unsigned i = 0; i < 128; i++)
    assert(wd179x_read(&f, 3) == 0x5a);
  assert(!(f.status & 0x1d));
  wd179x_write(&f, 2, 1);
  wd179x_write(&f, 0, 0x80);
  for (unsigned i = 0; i < 128; i++)
    assert(wd179x_read(&f, 3) == 0xa5);
  assert((f.status & 0x28) == 0x28);
  wd179x_write(&f, 2, 3);
  wd179x_write(&f, 0, 0xa0);
  wd179x_write(&f, 3, 0x34);
  wd179x_tick(&f, 1408);
  for (unsigned i = 1; i < 128; i++)
    wd179x_write(&f, 3, (uint8_t)i);
  assert(!(f.status & 0x1d));
  wd179x_write(&f, 0, 0x80);
  assert(wd179x_read(&f, 3) == 0x34);
  for (unsigned i = 1; i < 128; i++)
    assert(wd179x_read(&f, 3) == (uint8_t)i);
  wd179x_write(&f, 0, 0xc0);
  assert(wd179x_read(&f, 3) == 0);
  assert(wd179x_read(&f, 3) == 0);
  assert(wd179x_read(&f, 3) == 3);
  assert(wd179x_read(&f, 3) == 0);
  wd179x_write(&f, 0, 0xd0);
  f.fm_only = 0;
  wd179x_write(&f, 0, 0x80);
  assert(!(f.status & 2));
  for (unsigned i = 0; i < 6; i++) {
    wd179x_index(&f, 0);
    wd179x_index(&f, 1);
  }
  assert(f.status & 0x10);
  wd_disk *again = calloc(1, sizeof(*again));
  assert(!wd_disk_bind_image(again, dac_memory_storage(raw, n, 1), 1));
  uint8_t buffer[128];
  assert(!wd_disk_read_sector(again, 0, 0, 3, buffer) && buffer[0] == 0x34 &&
         buffer[127] == 127);
  free(again);
  /* FM formatting tokens, CRC generation and read-track encoding. */
  f.fm_only = 1;
  wd179x_write(&f, 0, 0xf0);
  wd179x_write(&f, 3, 0xff);
  wd179x_index(&f, 0);
  wd179x_index(&f, 1);
  unsigned count = 1;
  for (unsigned si = 0; si < 2; si++) {
    for (unsigned i = 0; i < 6; i++)
      track_write(&f, &count, 0);
    track_write(&f, &count, 0xfe);
    track_write(&f, &count, 0);
    track_write(&f, &count, 0);
    track_write(&f, &count, si ? 1 : 3);
    track_write(&f, &count, 0);
    track_write(&f, &count, 0xf7);
    for (unsigned i = 0; i < 6; i++)
      track_write(&f, &count, 0);
    track_write(&f, &count, 0xfb);
    for (unsigned i = 0; i < 128; i++)
      track_write(&f, &count, 0x6c);
    track_write(&f, &count, 0xf7);
  }
  while (count < 3125)
    track_write(&f, &count, 0xff);
  assert(!(f.status & 0x3d));
  assert(!wd_disk_sector_error(d, 0, 0, 1));
  wd179x_write(&f, 0, 0xe0);
  wd179x_index(&f, 0);
  wd179x_index(&f, 1);
  unsigned marks = 0;
  for (unsigned i = 0; i < 3125; i++)
    marks += wd179x_read(&f, 3) == 0xfe;
  assert(marks == 2 && !(f.status & 0x1d));
  /* Verify compares on-disk cylinder IDs, independently of physical position.
   */
  d->tracks[0].sector[0].cylinder = 7;
  d->tracks[0].sector[1].cylinder = 7;
  f.track = 7;
  f.data = 7;
  f.hlt_line = 1;
  wd179x_write(&f, 0, 0x14);
  wd179x_tick(&f, 60000);
  assert(f.physical_track == 0 && !(f.status & 0x11));
  f.track = 8;
  f.data = 8;
  wd179x_write(&f, 0, 0x14);
  wd179x_tick(&f, 60000);
  assert(f.status & 0x10);
  free(d);
  free(raw);
  image[6] = 0;
  assert(wd_disk_import(image, sizeof(image), &raw, &n) == -ENOTSUP);
  image[6] = 2;
  assert(wd_disk_import(image, sizeof(image) - 1, &raw, &n) < 0);
}
#include "juku_keyboard_test.inc"
int main(void) {
  profiles_test();
  keyboard_contacts_test();
  keyboard_snapshot_test();
  media_test();
  puts("PASS Juku profile lifecycle, port isolation, keyboards and FM/IMD "
       "transfers");
}
