#include "juk_disk.h"
#include <errno.h>
#include <string.h>

int juk_disk_bind(juk_disk* disk, dac_storage storage, int heads, int writable) {
  if (!disk || (heads != 1 && heads != 2)) return -EINVAL;
  dac_media media;
  int result = dac_media_init(&media, storage,
      (dac_geometry){JUK_TRACKS, (unsigned)heads, JUK_SECTORS_PER_TRACK,
                     JUK_SECTOR_SIZE, 1}, writable);
  if (result) return result;
  memset(disk, 0, sizeof(*disk));
  disk->heads = heads;
  disk->size = (long)storage.size;
  disk->writable = writable != 0;
  disk->media = media;
  return 0;
}
long juk_disk_offset(const juk_disk* disk, int track, int head, int sector) {
  uint64_t offset;
  if (!disk || dac_media_offset(&disk->media, (unsigned)track,
      (unsigned)head, (unsigned)sector, &offset)) return -1;
  return (long)offset;
}
static long metadata_index(const juk_disk* disk, int track, int head, int sector) {
  if (!disk || !disk->media.storage.read) return -1;
  if (track < 0 || track >= JUK_TRACKS) return -1;
  if (head < 0 || head >= disk->heads) return -1;
  if (sector < 1 || sector > JUK_SECTORS_PER_TRACK) return -1;
  return ((long)track * 2 + head) * JUK_SECTORS_PER_TRACK + (sector - 1);
}


int juk_disk_read_sector(juk_disk* disk, int t, int h, int s, uint8_t out[JUK_SECTOR_SIZE]) {
  if (!disk) return -EINVAL;
  return dac_media_read(&disk->media, (unsigned)t, (unsigned)h, (unsigned)s, out);
}
int juk_disk_write_sector(juk_disk* disk, int t, int h, int s, const uint8_t in[JUK_SECTOR_SIZE]) {
  if (!disk || !disk->writable) return -EROFS;
  return dac_media_write(&disk->media, (unsigned)t, (unsigned)h, (unsigned)s, in);
}
int juk_disk_sector_deleted(const juk_disk* disk, int track, int head, int sector) {
  long index = metadata_index(disk, track, head, sector);
  if (index < 0) return -EINVAL;
  return disk->deleted_data[index] != 0;
}


int juk_disk_set_sector_deleted(juk_disk* disk, int track, int head, int sector, int deleted) {
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
