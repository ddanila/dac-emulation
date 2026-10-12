/* Bounded raw/standard/extended DSK adapter. Original MIT implementation;
 * format definitions: https://cpctech.cpcwiki.de/docs/{dsk,extdsk}.html.
 * DSK stores ID order and GAP3, not measured angular positions or flux. */
#include "robotron.h"
#include <errno.h>
#include <stdlib.h>
#include <string.h>
static unsigned ticks(unsigned bytes) {
  return (unsigned)(((uint64_t)bytes * 79872 + 624) / 625);
}
static void positions(robotron_track *t) {
  unsigned id = 162;
  for (unsigned i = 0; i < t->count; i++) {
    t->sector[i].id_phase = ticks(id);
    t->sector[i].data_phase = ticks(id + 44);
    id += (128u << t->sector[i].n) + 62 + t->gap;
  }
}
static int parse(dac_storage s, robotron_track *tracks, unsigned *format) {
  uint8_t h[256];
  memset(tracks, 0, 160 * sizeof(*tracks));
  if (!s.read || s.size < 256 || s.size > 1048576 || s.read(s.user, 0, h, 256))
    return -EINVAL;
  int extended = !memcmp(h, "EXTENDED CPC DSK File\r\nDisk-Info\r\n", 34);
  int standard = !memcmp(h, "MV - CPCEMU Disk-File\r\nDisk-Info\r\n", 34);
  if (!extended && !standard) {
    if (s.size != 819200)
      return -EINVAL;
    *format = 0;
    for (unsigned t = 0; t < 160; t++) {
      tracks[t].count = 5;
      tracks[t].gap = 27;
      for (unsigned i = 0; i < 5; i++)
        tracks[t].sector[i] = (robotron_sector){.offset = (t * 5 + i) * 1024,
                                                .c = t / 2,
                                                .h = t % 2,
                                                .r = i + 1,
                                                .n = 3};
      positions(&tracks[t]);
    }
    return 0;
  }
  if (!h[0x30] || h[0x30] > 80 || !h[0x31] || h[0x31] > 2)
    return -EINVAL;
  *format = extended ? 2 : 1;
  unsigned offset = 256;
  for (unsigned t = 0; t < h[0x30] * h[0x31]; t++) {
    unsigned cylinder = t / h[0x31], side = t % h[0x31];
    unsigned length = extended ? h[0x34 + t] * 256u : h[0x32] + h[0x33] * 256u;
    if (!length && extended)
      continue;
    if (length < 256 || offset > s.size || length > s.size - offset)
      return -EINVAL;
    uint8_t b[256];
    if (s.read(s.user, offset, b, 256) || memcmp(b, "Track-Info\r\n", 12) ||
        b[0x10] != cylinder || b[0x11] != side ||
        b[0x15] > ROBOTRON_TRACK_SECTORS || b[0x14] > 5 || b[0x12] > 1 ||
        b[0x13] == 1 || b[0x13] > 2)
      return -EINVAL;
    robotron_track *tr = &tracks[cylinder * 2 + side];
    tr->header = offset;
    tr->count = b[0x15];
    tr->gap = b[0x16];
    unsigned data = offset + 256, capacity = 146;
    for (unsigned i = 0; i < tr->count; i++) {
      const uint8_t *id = b + 0x18 + 8 * i;
      unsigned bytes = id[3] <= 5 ? 128u << id[3] : 0;
      if (!bytes || (!extended && id[3] != b[0x14]) ||
          (extended && (id[6] + 256u * id[7]) != bytes) ||
          data + bytes > offset + length || (id[4] & ~0x25) || (id[5] & ~0x61))
        return -EINVAL;
      tr->sector[i] = (robotron_sector){.offset = data,
                                        .c = id[0],
                                        .h = id[1],
                                        .r = id[2],
                                        .n = id[3],
                                        .st1 = id[4],
                                        .st2 = id[5]};
      data += bytes;
      capacity += bytes + 62 + tr->gap;
    }
    if (capacity > 6250)
      return -EINVAL;
    positions(tr);
    offset += length;
  }
  return offset == s.size ? 0 : -EINVAL;
}
int robotron_disk_validate(dac_storage s) {
  robotron_track *tracks = malloc(160 * sizeof(*tracks));
  unsigned format;
  if (!tracks)
    return -ENOMEM;
  int r = parse(s, tracks, &format);
  free(tracks);
  return r;
}
int robotron_disk_unit(robotron *m, unsigned u, dac_storage s, int writable) {
  if (!m || u > 1 || (writable && s.read && !s.write))
    return -EINVAL;
  dac_media *d = u ? &m->disk_b : &m->disk;
  if (!s.read) {
    memset(d, 0, sizeof(*d));
    memset(m->tracks[u], 0, sizeof(m->tracks[u]));
    m->disk_format[u] = 0;
    return 0;
  }
  robotron_track *tracks = malloc(sizeof(m->tracks[u]));
  unsigned format;
  if (!tracks)
    return -ENOMEM;
  int r = parse(s, tracks, &format);
  if (!r) {
    memcpy(m->tracks[u], tracks, sizeof(m->tracks[u]));
    m->disk_format[u] = format;
    *d = (dac_media){s, {80, 2, 5, 1024, 1}, !!writable};
  }
  free(tracks);
  return r;
}
int robotron_disk(robotron *m, dac_storage s, int writable) {
  return robotron_disk_unit(m, 0, s, writable);
}
/* Formatting is bounded by the allocated track: never shift another track's
 * backing bytes. Each completed sector can persist independently. */
static int format_valid(robotron *m, unsigned u, unsigned cylinder,
                        unsigned head, const uint8_t *id, unsigned gap,
                        unsigned slot) {
  if (u > 1 || cylinder >= 80 || head > 1 || gap > 255)
    return -EINVAL;
  robotron_track *tr = &m->tracks[u][cylinder * 2 + head];
  if (slot >= tr->count || id[3] != tr->sector[slot].n)
    return -EINVAL;
  unsigned capacity = 146;
  for (unsigned i = 0; i < tr->count; i++)
    capacity += (128u << tr->sector[i].n) + 62 + gap;
  if (capacity > 6250)
    return -EINVAL;
  if (!m->disk_format[u] &&
      (id[0] != cylinder || id[1] != head || id[2] != slot + 1))
    return -EINVAL;
  return 0;
}
int robotron_format_sector(robotron *m, unsigned u, unsigned cylinder,
                           unsigned head, const uint8_t *id, unsigned gap,
                           unsigned fill, unsigned slot) {
  int err = format_valid(m, u, cylinder, head, id, gap, slot);
  if (err)
    return err;
  dac_media *d = u ? &m->disk_b : &m->disk;
  if (!d->writable || !d->storage.write)
    return -EROFS;
  robotron_track *tr = &m->tracks[u][cylinder * 2 + head];
  robotron_sector *s = &tr->sector[slot];
  uint8_t b[4096];
  memset(b, fill, sizeof(b));
  if (d->storage.write(d->storage.user, s->offset, b, 128u << s->n))
    return -EIO;
  if (m->disk_format[u]) {
    uint8_t h[256];
    if (d->storage.read(d->storage.user, tr->header, h, 256))
      return -EIO;
    h[0x16] = gap;
    h[0x17] = fill;
    memcpy(h + 0x18 + 8 * slot, id, 4);
    h[0x1c + 8 * slot] = h[0x1d + 8 * slot] = 0;
    if (d->storage.write(d->storage.user, tr->header, h, 256))
      return -EIO;
    s->c = id[0];
    s->h = id[1];
    s->r = id[2];
    s->n = id[3];
    tr->gap = gap;
    positions(tr);
  }
  s->st1 = s->st2 = 0;
  return 0;
}
int robotron_format_track(robotron *m, unsigned u, unsigned cylinder,
                          unsigned head, const uint8_t *ids, unsigned gap,
                          unsigned fill) {
  if (u > 1 || cylinder >= 80 || head > 1)
    return -EINVAL;
  unsigned count = m->tracks[u][cylinder * 2 + head].count;
  if (!count)
    return -EINVAL;
  for (unsigned i = 0; i < count; i++) {
    int err = format_valid(m, u, cylinder, head, ids + 4 * i, gap, i);
    if (err)
      return err;
  }
  for (unsigned i = 0; i < count; i++) {
    int err =
        robotron_format_sector(m, u, cylinder, head, ids + 4 * i, gap, fill, i);
    if (err)
      return err;
  }
  return 0;
}
