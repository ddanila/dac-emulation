#ifndef DAC_ROBOTRON_H
#define DAC_ROBOTRON_H
#include "../../common/cpu/z80.h"
#include "../../common/media/media.h"
#include "../../common/trace/trace.h"
#include <stddef.h>
/* Experimental functional PC-1715W/1715M profile. See README for fidelity. */
typedef struct {
  uint8_t command[9], result[7], data[16384];
  unsigned cmd_len, cmd_pos, result_len, result_pos, phase, data_pos, data_len;
  unsigned cylinder[4], unit, head, sector, n, eot, pending, st0, write;
  int scan_compare;
  unsigned scan_mode, tc, reset;
  uint64_t ready_at;
} robotron_fdc;
typedef struct {
  uint16_t a, b, count, run_a, run_b;
  unsigned remaining, transferred;
  uint8_t tags[10], tag_count, tag_pos, a_mode, b_mode, a_io, b_io, direction;
  uint8_t enabled, irq_enabled, irq, vector, status, mask, read_pos,
      mask_pending, force_ready, ready_high, irq_control, irq_vector,
      in_service;
} robotron_dma;
typedef struct {
  uint8_t control, constant, waiting, pending, in_service;
  unsigned counter, prescaler;
} robotron_timer;
typedef struct {
  dac_z80 cpu;
  dac_trace_sink trace;
  uint8_t rom[2048], chargen[4096], vram[4096], ram[262144], prom[256], bank,
      krfd, motor;
  robotron_fdc fdc;
  robotron_dma dma;
  robotron_timer ctc[8];
  uint8_t ctc_vector[2];
  dac_media disk;
  uint8_t sio_pointer[2], sio_regs[2][8];
  uint8_t keys[256];
  unsigned key_read, key_write;
  uint64_t disk_reads, disk_writes, video_writes;
  uint8_t crtc[4], crtc_pos, crtc_end, display_on, crtc_status, cursor[2];
} robotron;
void robotron_init(robotron *);
int robotron_load(robotron *, const void *rom, size_t, const void *prom,
                  size_t);
int robotron_disk(robotron *, dac_storage, int writable);
void robotron_run(robotron *, unsigned);
/* pixels must hold 640*384 entries; dimensions are returned after rendering. */
void robotron_video(robotron *, uint32_t *pixels, unsigned *width,
                    unsigned *height);
int robotron_key(robotron *, uint8_t);
uint8_t robotron_read(void *, uint16_t);
void robotron_write(void *, uint16_t, uint8_t);
uint8_t robotron_input(void *, uint16_t);
void robotron_output(void *, uint16_t, uint8_t);
#endif
