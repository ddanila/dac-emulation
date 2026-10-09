#include "media.h"
#include <errno.h>
#include <string.h>

int dac_media_init(dac_media *m, dac_storage s, dac_geometry g, int writable) {
  if (!m || !s.read || !g.tracks || !g.heads || !g.sectors || !g.sector_size)
    return -EINVAL;
  uint64_t size = g.tracks;
  unsigned factors[] = {g.heads, g.sectors, g.sector_size};
  for (unsigned i = 0; i < 3; i++) {
    if (size > UINT64_MAX / factors[i]) return -EOVERFLOW;
    size *= factors[i];
  }
  if (size != s.size || (writable && !s.write)) return -EINVAL;
  *m = (dac_media){s, g, writable != 0};
  return 0;
}
int dac_media_offset(const dac_media *m, unsigned t, unsigned h, unsigned s,
                     uint64_t *offset) {
  if (!m || !offset || !m->storage.read || t >= m->geometry.tracks ||
      h >= m->geometry.heads || s < m->geometry.first_sector ||
      s - m->geometry.first_sector >= m->geometry.sectors) return -EINVAL;
  *offset = (((uint64_t)t * m->geometry.heads + h) * m->geometry.sectors +
             s - m->geometry.first_sector) * m->geometry.sector_size;
  return 0;
}
int dac_media_read(const dac_media *m, unsigned t, unsigned h, unsigned s, void *p) {
  uint64_t offset;
  int result = dac_media_offset(m, t, h, s, &offset);
  if (result || !p) return result ? result : -EINVAL;
  return m->storage.read(m->storage.user, offset, p, m->geometry.sector_size);
}
int dac_media_write(dac_media *m, unsigned t, unsigned h, unsigned s, const void *p) {
  if (!m || !m->writable) return -EROFS;
  uint64_t offset;
  int result = dac_media_offset(m, t, h, s, &offset);
  if (result || !p) return result ? result : -EINVAL;
  return m->storage.write(m->storage.user, offset, p, m->geometry.sector_size);
}
static int memory_read(void *p, uint64_t offset, void *out, size_t size) {
  memcpy(out, (const uint8_t *)p + (size_t)offset, size);
  return 0;
}
static int memory_write(void *p, uint64_t offset, const void *in, size_t size) {
  memcpy((uint8_t *)p + (size_t)offset, in, size);
  return 0;
}
dac_storage dac_memory_storage(void *p, size_t size, int writable) {
  return (dac_storage){p, size, p ? memory_read : NULL,
                       p && writable ? memory_write : NULL};
}
