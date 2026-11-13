#include "wd_disk.h"
#include <errno.h>
#include <string.h>

int wd_disk_bind(wd_disk* disk, dac_storage storage, int heads, int writable) {
  return wd_disk_bind_geometry(disk, storage,
      (dac_geometry){JUK_TRACKS, (unsigned)heads, JUK_SECTORS_PER_TRACK, JUK_SECTOR_SIZE, 1}, writable);
}
int wd_disk_bind_geometry(wd_disk* disk, dac_storage storage, dac_geometry geometry, int writable) {
  if (!disk || geometry.tracks>80 || !geometry.heads || geometry.heads>2 ||
      geometry.sectors!=10 || geometry.sector_size!=512 || geometry.first_sector>1) return -EINVAL;
  dac_media media;
  int result = dac_media_init(&media, storage, geometry, writable);
  if (result) return result;
  memset(disk, 0, sizeof(*disk));
  disk->heads = (int)geometry.heads;
  disk->size = (long)storage.size;
  disk->writable = writable != 0;
  disk->media = media;
  return 0;
}
long wd_disk_offset(const wd_disk* disk, int track, int head, int sector) {
  uint64_t offset;
  if (!disk || dac_media_offset(&disk->media, (unsigned)track,
      (unsigned)head, (unsigned)sector, &offset)) return -1;
  return (long)offset;
}
static long metadata_index(const wd_disk* disk, int track, int head, int sector) {
  if (!disk || !disk->media.storage.read) return -1;
  if (track < 0 || track >= (int)disk->media.geometry.tracks) return -1;
  if (head < 0 || head >= disk->heads) return -1;
  sector -= (int)disk->media.geometry.first_sector;
  if (sector < 0 || sector >= JUK_SECTORS_PER_TRACK) return -1;
  return ((long)track * 2 + head) * JUK_SECTORS_PER_TRACK + sector;
}


int wd_disk_read_sector(wd_disk* disk, int t, int h, int s, uint8_t out[JUK_SECTOR_SIZE]) {
  if (!disk) return -EINVAL;
  return dac_media_read(&disk->media, (unsigned)t, (unsigned)h, (unsigned)s, out);
}
int wd_disk_write_sector(wd_disk* disk, int t, int h, int s, const uint8_t in[JUK_SECTOR_SIZE]) {
  if (!disk || !disk->writable) return -EROFS;
  return dac_media_write(&disk->media, (unsigned)t, (unsigned)h, (unsigned)s, in);
}
int wd_disk_sector_deleted(const wd_disk* disk, int track, int head, int sector) {
  long index = metadata_index(disk, track, head, sector);
  if (index < 0) return -EINVAL;
  return disk->deleted_data[index] != 0;
}


int wd_disk_set_sector_deleted(wd_disk* disk, int track, int head, int sector, int deleted) {
  if (!disk || !disk->writable) return -EROFS;
  long index = metadata_index(disk, track, head, sector);
  if (index < 0) return -EINVAL;
  uint8_t value = deleted != 0;
  if (disk->marks.write) {
    int result = disk->marks.write(disk->marks.user, (uint64_t)index, &value, 1);
    if (result) return result;
  }
  disk->deleted_data[index] = value;
  return 0;
}
