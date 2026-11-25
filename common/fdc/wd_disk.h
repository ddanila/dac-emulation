#ifndef DAC_WD_DISK_H
#define DAC_WD_DISK_H

#include <stdint.h>
#include "../media/media.h"

#define JUK_TRACKS 80
#define JUK_SECTORS_PER_TRACK 10
#define JUK_SECTOR_SIZE 512
#define JUK_MFM_TRACK_SIZE 6250
#define JUK_DELETED_MARK_COUNT (JUK_TRACKS * 2 * JUK_SECTORS_PER_TRACK)
#define JUK_SINGLE_SIDED_SIZE (JUK_TRACKS * 1 * JUK_SECTORS_PER_TRACK * JUK_SECTOR_SIZE)
#define JUK_DOUBLE_SIDED_SIZE (JUK_TRACKS * 2 * JUK_SECTORS_PER_TRACK * JUK_SECTOR_SIZE)

#define WD_MAX_SECTORS 32
#define WD_MAX_SECTOR_SIZE 2048
typedef struct { uint32_t offset; uint8_t id, cylinder, head, code, type; } wd_sector;
typedef struct { uint8_t count, fm; wd_sector sector[WD_MAX_SECTORS]; } wd_track;
typedef struct {
  unsigned imd;
  wd_track tracks[160];
  void* fp; /* native adapter ownership only; NULL for borrowed storage */
  dac_media media;
  void* deleted_marks_fp; /* native adapter ownership only */
  dac_storage marks;
  int heads;
  long size;
  int writable;
  // The historical raw image stores payload bytes only. Preserve data-address
  // mark type in memory, optionally backed by an explicitly attached companion
  // file, without pretending the metadata is part of the raw image.
  uint8_t deleted_data[80 * 2 * 32];
} wd_disk;

/* Imports raw JUK or IMD into an owned, writable, uncompressed image copy.
 * IMD supports 250k controller rate, up to 80 cylinders, two sides, 32 IDs
 * per track and 128..2048-byte sectors; unsupported features return ENOTSUP. */
int wd_disk_import(const void *, size_t, uint8_t **, size_t *);
int wd_disk_bind_image(wd_disk *, dac_storage, int writable);
unsigned wd_disk_sector_size(const wd_disk *, int, int, int);
unsigned wd_disk_sector_count(const wd_disk *, int, int);
int wd_disk_sector_id(const wd_disk *, int, int, unsigned);
int wd_disk_encoding(const wd_disk *, int, int);
int wd_disk_sector_error(const wd_disk *, int, int, int);
int wd_disk_id(const wd_disk *, int, int, int, uint8_t out[4]);
int wd_disk_bind_geometry(wd_disk*, dac_storage, dac_geometry, int writable);
int wd_disk_bind(wd_disk*, dac_storage, int heads, int writable);
int wd_disk_open(wd_disk* disk, const char* path);
int wd_disk_open_writable(wd_disk* disk, const char* path);
int wd_disk_attach_deleted_marks(wd_disk* disk, const char* path);
void wd_disk_close(wd_disk* disk);
long wd_disk_offset(const wd_disk* disk, int track, int head, int sector);
int wd_disk_read_sector(wd_disk* disk, int track, int head, int sector, uint8_t *out);
int wd_disk_write_sector(wd_disk* disk, int track, int head, int sector,
                          const uint8_t *in);
int wd_disk_sector_deleted(const wd_disk* disk, int track, int head, int sector);
int wd_disk_set_sector_deleted(wd_disk* disk, int track, int head, int sector, int deleted);

#endif
