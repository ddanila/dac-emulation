#include "../../machines/juku/juk_disk.h"

#include <errno.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int file_read(void *p, uint64_t offset, void *out, size_t count) {
  FILE *fp = p;
  if (offset > LONG_MAX)
    return -EOVERFLOW;
  if (fseek(fp, (long)offset, SEEK_SET) != 0)
    return errno ? -errno : -EIO;
  size_t got = fread(out, 1, count, fp);
  return got == count ? 0 : (ferror(fp) ? -EIO : -EINVAL);
}
static int file_write(void *p, uint64_t offset, const void *in, size_t count) {
  FILE *fp = p;
  if (offset > LONG_MAX)
    return -EOVERFLOW;
  if (fseek(fp, (long)offset, SEEK_SET) != 0)
    return errno ? -errno : -EIO;
  if (fwrite(in, 1, count, fp) != count)
    return -EIO;
  return fflush(fp) == 0 ? 0 : (errno ? -errno : -EIO);
}

static long file_size(FILE *fp) {
  long here = ftell(fp);
  if (here < 0)
    return -1;
  if (fseek(fp, 0, SEEK_END) != 0)
    return -1;
  long size = ftell(fp);
  if (size < 0)
    return -1;
  if (fseek(fp, here, SEEK_SET) != 0)
    return -1;
  return size;
}

static int open_mode(juk_disk *disk, const char *path, int writable) {
  memset(disk, 0, sizeof(*disk));
  FILE *fp = fopen(path, writable ? "r+b" : "rb");
  if (!fp)
    return -errno;

  long size = file_size(fp);
  uint8_t magic[4];
  if (size < 4 || file_read(fp, 0, magic, 4)) {
    fclose(fp);
    return -EINVAL;
  }
  if (!memcmp(magic, "IMD ", 4)) {
    if (size > 2 * 1024 * 1024) {
      fclose(fp);
      return -EFBIG;
    }
    uint8_t *input = malloc((size_t)size), *output = NULL;
    size_t length = 0;
    if (!input) {
      fclose(fp);
      return -ENOMEM;
    }
    int r = file_read(fp, 0, input, (size_t)size);
    fclose(fp);
    if (!r)
      r = wd_disk_import(input, (size_t)size, &output, &length);
    free(input);
    if (r)
      return r;
    fp = tmpfile();
    if (!fp) {
      free(output);
      return -errno;
    }
    r = file_write(fp, 0, output, length);
    free(output);
    if (r) {
      fclose(fp);
      return r;
    }
    size = (long)length;
  }
  dac_storage storage = {fp, (uint64_t)size, file_read, file_write};
  int r = wd_disk_bind_image(disk, storage, writable);
  if (r) {
    fclose(fp);
    return r;
  }
  disk->fp = fp;
  return 0;
}

int juk_disk_open(juk_disk *disk, const char *path) {
  return open_mode(disk, path, 0);
}

int juk_disk_open_writable(juk_disk *disk, const char *path) {
  return open_mode(disk, path, 1);
}

int juk_disk_attach_deleted_marks(juk_disk *disk, const char *path) {
  if (!disk || disk->imd || !disk->fp || !path || !path[0])
    return -EINVAL;
  if (disk->deleted_marks_fp)
    return -EBUSY;

  FILE *fp = fopen(path, disk->writable ? "r+b" : "rb");
  if (!fp && disk->writable && errno == ENOENT) {
    fp = fopen(path, "w+b");
    if (!fp)
      return -errno;
    uint8_t empty[JUK_DELETED_MARK_COUNT] = {0};
    if (fwrite(empty, 1, sizeof(empty), fp) != sizeof(empty) ||
        fflush(fp) != 0) {
      int saved_errno = errno;
      fclose(fp);
      return saved_errno ? -saved_errno : -EIO;
    }
    if (fseek(fp, 0, SEEK_SET) != 0) {
      int saved_errno = errno;
      fclose(fp);
      return saved_errno ? -saved_errno : -EIO;
    }
  } else if (!fp) {
    return -errno;
  }

  if (file_size(fp) != JUK_DELETED_MARK_COUNT) {
    fclose(fp);
    return -EINVAL;
  }
  if (fread(disk->deleted_data, 1, JUK_DELETED_MARK_COUNT, fp) !=
      JUK_DELETED_MARK_COUNT) {
    fclose(fp);
    memset(disk->deleted_data, 0, sizeof(disk->deleted_data));
    return -EIO;
  }
  for (int i = 0; i < JUK_DELETED_MARK_COUNT; i++) {
    if (disk->deleted_data[i] > 1) {
      fclose(fp);
      memset(disk->deleted_data, 0, sizeof(disk->deleted_data));
      return -EINVAL;
    }
  }
  disk->deleted_marks_fp = fp;
  disk->marks =
      (dac_storage){fp, JUK_DELETED_MARK_COUNT, file_read, file_write};
  return 0;
}

void juk_disk_close(juk_disk *disk) {
  /* IMD runs on a private normalized copy. Export is explicit, never an
   * implicit rewrite of a historical source image. */
  const char *export_path = getenv("JUKU_DISK_EXPORT");
  if (disk->imd && disk->fp && export_path && *export_path) {
    FILE *out = fopen(export_path, "wb");
    int failed = !out;
    uint8_t bytes[4096];
    for (long pos = 0; !failed && pos < disk->size;
         pos += (long)sizeof(bytes)) {
      size_t count = (size_t)(disk->size - pos);
      if (count > sizeof(bytes))
        count = sizeof(bytes);
      failed = file_read(disk->fp, (uint64_t)pos, bytes, count) ||
               fwrite(bytes, 1, count, out) != count;
    }
    if (out && fclose(out))
      failed = 1;
    if (failed)
      fprintf(stderr, "Could not export IMD session to %s\n", export_path);
  }
  if (disk->deleted_marks_fp)
    fclose(disk->deleted_marks_fp);
  if (disk->fp)
    fclose(disk->fp);
  memset(disk, 0, sizeof(*disk));
}
