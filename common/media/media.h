#ifndef DAC_MEDIA_H
#define DAC_MEDIA_H
#include <stddef.h>
#include <stdint.h>

/* Borrowed storage. Callbacks return zero on success, negative errno on error.
 * The owner controls lifetime, persistence and closing. */
typedef struct {
  void *user;
  uint64_t size;
  int (*read)(void *, uint64_t, void *, size_t);
  int (*write)(void *, uint64_t, const void *, size_t);
} dac_storage;
typedef struct {
  unsigned tracks, heads, sectors, sector_size, first_sector;
} dac_geometry;
typedef struct {
  dac_storage storage;
  dac_geometry geometry;
  int writable;
} dac_media;
int dac_media_init(dac_media *, dac_storage, dac_geometry, int writable);
int dac_media_offset(const dac_media *, unsigned, unsigned, unsigned, uint64_t *);
int dac_media_read(const dac_media *, unsigned, unsigned, unsigned, void *);
int dac_media_write(dac_media *, unsigned, unsigned, unsigned, const void *);
/* In-memory storage borrows bytes; caller keeps them alive. */
dac_storage dac_memory_storage(void *bytes, size_t size, int writable);
#endif
