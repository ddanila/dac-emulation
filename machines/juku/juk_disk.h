/* Compatibility API; shared WD179x implementation. */
#include "../../common/fdc/wd_disk.h"
#define juk_disk wd_disk
#define juk_disk_attach_deleted_marks wd_disk_attach_deleted_marks
#define juk_disk_bind wd_disk_bind
#define juk_disk_close wd_disk_close
#define juk_disk_offset wd_disk_offset
#define juk_disk_open wd_disk_open
#define juk_disk_open_writable wd_disk_open_writable
#define juk_disk_read_sector wd_disk_read_sector
#define juk_disk_sector_deleted wd_disk_sector_deleted
#define juk_disk_set_sector_deleted wd_disk_set_sector_deleted
#define juk_disk_write_sector wd_disk_write_sector
