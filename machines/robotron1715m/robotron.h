#ifndef DAC_ROBOTRON_H
#define DAC_ROBOTRON_H
#include "../../common/cpu/z80.h"
#include "../../common/media/media.h"
#include "../../common/trace/trace.h"
#include "keyboard.h"
#include <stddef.h>
#define ROBOTRON_REVOLUTION_TICKS 798720u /* 3.9936 MHz / 5 Hz */
#define ROBOTRON_SPINUP_TICKS                                                  \
  1597440u                           /* Reference profile: 400 ms linear ramp */
#define ROBOTRON_SETTLE_TICKS 59904u /* Reference upper bound: 15 ms */
#define ROBOTRON_STEP_TICKS 11981u   /* Reference travel duration: 3 ms */
#define ROBOTRON_HEAD_LOAD_TICKS 199680u /* Reference upper bound: 50 ms */
#define ROBOTRON_STEP_EVENTS 64u
/* Bounded 250 kbit/s MFM DSK tracks; no flux or weak-sector synthesis. */
#define ROBOTRON_TRACK_SECTORS 29u
typedef struct {
  uint32_t offset, id_phase, data_phase;
  uint8_t c, h, r, n, st1, st2;
} robotron_sector;
typedef struct {
  uint32_t header; /* Zero for raw images/unallocated tracks. */
  unsigned count, gap;
  robotron_sector sector[ROBOTRON_TRACK_SECTORS];
} robotron_track;
typedef struct {
  unsigned speed, fraction, index_count, ready_indexes, ready;
  uint64_t last_index, load_at, unload_at, settle_at, step_at;
  unsigned loaded, from_q16, door_open, ejected;
  uint64_t events[ROBOTRON_STEP_EVENTS];
} robotron_drive;
typedef struct {
  uint8_t code[80], fifo[16];
  unsigned overflow, bytes, stop_screen, ignore_screen;
  unsigned field, end_screen, columns, lines;
  uint8_t pixels[80][16], highlight[80][16];
} robotron_video_row;
/* Functional display-board scheduler. Nominal 13.824 MHz dot clock / 8;
 * local memory response is idealized, not the system floppy DMA. */
typedef struct {
  unsigned fraction, character, row, frames, stream, remaining;
  unsigned overflow, stopped, underrun, blank_from, dma, ignored;
  robotron_video_row pending_row, scanout[24];
  unsigned pending_valid, valid_rows, field, end_screen;
  unsigned fetch_col, fetch_columns, fetch_fifo, fetch_phase, fetch_ignored;
  unsigned fetch_invisible, fetch_wait;
} robotron_raster;
/* Experimental functional PC-1715W/1715M profile. See README for fidelity. */
typedef struct {
  uint8_t command[9], result[7], data[16384];
  unsigned cmd_len, cmd_pos, result_len, result_pos, phase, data_pos, data_len;
  unsigned cylinder[4], unit, head, sector, n, eot, pending, st0, write;
  int scan_compare;
  unsigned scan_mode, tc, reset, reset_queue, formatting;
  uint64_t ready_at, seek_at[4];
  unsigned seek_target[4], seeking, seek_done, step_ticks;
  unsigned seek_interval[4], steps[4], physical[4], recalibrate[4], pulses[4],
      seek_status[4];
  unsigned head_load_ticks, head_unload_ticks;
  unsigned search, search_index, read_id, slot, result_c, id_head, error2;
  uint64_t byte_origin;
  unsigned read_track, track_count, track_match, track_st1, track_st2;
  unsigned write_fault;
} robotron_fdc;
typedef struct {
  uint16_t a, b, count, run_a, run_b;
  unsigned remaining, transferred;
  uint8_t tags[10], tag_count, tag_pos, a_mode, b_mode, a_io, b_io, direction;
  uint8_t enabled, irq_enabled, irq, vector, status, mask, read_pos,
      mask_pending, force_ready, ready_high, irq_control, irq_vector,
      in_service;
  uint8_t a_timing, b_timing, phase, ticks, latch;
  uint8_t operation, search_mask, match, stop_match, wait_enabled, wait;
  uint8_t auto_restart, mode, bus_owned, release;
} robotron_dma;
typedef struct {
  uint8_t control, constant, waiting, pending, in_service;
  unsigned counter, prescaler;
} robotron_timer;
typedef struct {
  uint8_t fifo[3], read, count, errors, phase, bits, byte, parity;
  unsigned wait;
  uint8_t pending, in_service, first;
} robotron_sio_rx;
typedef struct {
  dac_z80 cpu;
  dac_trace_sink trace;
  unsigned
      trace_master; /* transient CPU/DMA attribution, zero outside run DMA */
  robotron_keyboard keyboard;
  robotron_sio_rx rx, rx_b;
  unsigned serial_events;
  uint8_t serial_levels[4];
  struct {
    uint8_t input[65536], output[65536];
    unsigned read, count, size, overflow, signals;
    unsigned frame, bits, clocks;
    uint8_t holding, shift, full, pending, in_service;
    unsigned tx_clocks, tx_halves;
    unsigned peer_baud, peer_format, peer_phase;
    unsigned ext_pending, ext_service, ext_latched, ext_signals;
    uint8_t fifo_errors[3], frame_errors;
    unsigned break_active, break_latched, rx_locked;
    unsigned tx_subclock;
    unsigned tx_frame, tx_elapsed, tx_div, decode_phase, decoded_size,
        decoded_overflow;
    uint8_t decoded[65536];
    robotron_sio_rx decoder;
  } v24;
  unsigned disconnected; /* bit0 keyboard power/data; bit1 monitor video */
  unsigned keyboard_enabled;
  uint8_t rom[2048], chargen[4096], vram[4096], ram[262144], prom[256], bank,
      krfd, motor;
  robotron_fdc fdc;
  unsigned rotation[2]; /* Phase in CPU ticks at nominal speed. */
  robotron_drive drive[2];
  robotron_track tracks[2][160];
  unsigned disk_format[2]; /* 0 raw, 1 standard DSK, 2 extended DSK */
  robotron_dma dma;
  robotron_timer ctc[8];
  uint8_t ctc_vector[2];
  dac_media disk, disk_b;
  uint8_t printer[65536];
  unsigned printer_size, printer_overflow, printer_state, printer_dropped;
  unsigned printer_accept, printer_ext_pending, printer_ext_service,
      printer_ext_latched, printer_cts_latched;
  uint8_t tx_holding, tx_shift, tx_full, tx_pending, tx_in_service;
  unsigned tx_clocks, tx_halves;
  uint8_t sio_pointer[2], sio_regs[2][8];
  uint8_t keys[256];
  unsigned key_read, key_write;
  uint64_t disk_reads, disk_writes, video_writes;
  robotron_raster raster;
  uint8_t crtc[4], crtc_pos, crtc_end, display_on, crtc_status, cursor[2];
} robotron;
void robotron_init(robotron *);
int robotron_keyboard_load(robotron *, const void *, size_t);
void robotron_serial_clock(void *, unsigned);
void robotron_v24_peer_tick(robotron *);
void robotron_v24_signals(robotron *, unsigned);
void robotron_v24_receive_clock(robotron *, unsigned);
void robotron_v24_clock(robotron *);
/* Native ideal-clock fixture: channel A/B, RX/TX, clock level, RX data. */
void robotron_serial_edge(robotron *, unsigned channel, unsigned transmit,
                          unsigned level, unsigned input);
void robotron_v24_transmit_clock(robotron *);
uint8_t robotron_v24_read(robotron *, unsigned);
uint8_t robotron_sio_read(robotron *, unsigned);
void robotron_sio_control(robotron *, unsigned, uint8_t);
void robotron_printer_state(robotron *, unsigned);
unsigned robotron_printer_cts(robotron *);
void robotron_printer_clock(robotron *);
int robotron_load(robotron *, const void *rom, size_t, const void *prom,
                  size_t);
int robotron_disk(robotron *, dac_storage, int writable);
int robotron_disk_unit(robotron *, unsigned, dac_storage, int writable);
void robotron_run(robotron *, unsigned);
void robotron_flush_interrupted_write(robotron *);
void robotron_drive_door(robotron *, unsigned, unsigned);
unsigned robotron_drive_ready(const robotron *, unsigned);
unsigned robotron_head_position(const robotron *, unsigned); /* cylinder Q16 */
int robotron_disk_validate(dac_storage);
int robotron_format_sector(robotron *, unsigned, unsigned, unsigned,
                           const uint8_t *, unsigned, unsigned, unsigned);
int robotron_format_track(robotron *, unsigned, unsigned, unsigned,
                          const uint8_t *, unsigned, unsigned);
/* pixels must hold 640*384 entries; dimensions are returned after rendering. */
void robotron_video(robotron *, uint32_t *pixels, unsigned *width,
                    unsigned *height);
int robotron_key(robotron *, uint8_t);
uint8_t robotron_peek(void *, uint16_t);
unsigned robotron_mapping(robotron *, uint16_t, unsigned);
uint8_t robotron_read(void *, uint16_t);
void robotron_write(void *, uint16_t, uint8_t);
uint8_t robotron_input(void *, uint16_t);
void robotron_output(void *, uint16_t, uint8_t);
void robotron_rebind(robotron *);
#endif
