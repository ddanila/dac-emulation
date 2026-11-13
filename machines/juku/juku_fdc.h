#include "juk_disk.h"
/* Compatibility API; shared WD179x implementation. */
#include "../../common/fdc/wd179x.h"
#define juk_disk wd_disk
#define juk_disk_offset wd_disk_offset
#define juk_disk_read_sector wd_disk_read_sector
#define juk_disk_sector_deleted wd_disk_sector_deleted
#define juk_disk_set_sector_deleted wd_disk_set_sector_deleted
#define juk_disk_write_sector wd_disk_write_sector
#define juku_fdc wd179x
#define juku_fdc_hlt wd179x_hlt
#define juku_fdc_index wd179x_index
#define juku_fdc_init wd179x_init
#define juku_fdc_portc wd179x_portc
#define juku_fdc_read wd179x_read
#define juku_fdc_ready wd179x_ready
#define juku_fdc_tick wd179x_tick
#define juku_fdc_tr00 wd179x_tr00
#define juku_fdc_write wd179x_write
