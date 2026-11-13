#ifndef DAC_WD179X_H
#define DAC_WD179X_H

#include <stdint.h>

#include "wd_disk.h"

typedef struct {
  wd_disk* disk;
  int enabled;
  unsigned paced_data, byte_delay, lost_position;
  int head;
  int drive;
  int motor_on;
  int clock_2mhz;
  uint8_t status;
  uint8_t track;
  uint8_t physical_track;
  uint8_t sector;
  uint8_t data;
  uint8_t command;
  int step_dir_in;
  uint8_t buffer[JUK_MFM_TRACK_SIZE];
  unsigned buffer_pos;
  unsigned buffer_len;
  int write_transfer;
  int write_track_transfer;
  int read_address_transfer;
  int read_track_transfer;
  int multi_record;
  unsigned write_track_output_pos;
  int write_track_state;
  unsigned write_track_field_pos;
  uint8_t write_track_id[4];
  int write_track_pending_sector;
  int write_track_pending_deleted;
  uint16_t write_track_seen;
  int write_track_format_error;
  int track_waiting_index;
  int write_track_preloaded;
  uint8_t write_track_preload;
  int command_delay_pending;
  unsigned command_delay_ticks;
  uint8_t command_delay_command;
  int command_hlt_pending;
  uint8_t command_hlt_command;
  int write_sector_lead_pending;
  unsigned write_sector_lead_ticks;
  int write_sector_preloaded;
  uint8_t write_sector_preload;
  int side_compare_pending;
  unsigned side_compare_index_pulses;
  int id_search_pending;
  unsigned id_search_index_pulses;
  unsigned drq_ticks;
  int write_first_byte_pending;
  int type_i_pending;
  unsigned type_i_ticks;
  unsigned type_i_rate_ticks;
  unsigned type_i_steps_remaining;
  int type_i_settling;
  int type_i_hlt_pending;
  int type_i_verify_pending;
  unsigned type_i_verify_index_pulses;
  uint8_t type_i_command;
  uint8_t force_interrupt_mask;
  int status_type_i;
  int head_loaded;
  unsigned idle_index_pulses;
  int hlt_line;
  int tr00_line;
  int ready_line;
  int index_line;
  int intrq;
} wd179x;

void wd179x_init(wd179x* fdc, wd_disk* disk);
void wd179x_portc(wd179x* fdc, uint8_t portc);
void wd179x_hlt(wd179x* fdc, int hlt);
void wd179x_tr00(wd179x* fdc, int tr00);
void wd179x_ready(wd179x* fdc, int ready);
void wd179x_index(wd179x* fdc, int index);
// Advance CPU-equivalent controller timers. D26 PC3/D95 selects the D93 clock:
// Type-I and head-settle intervals double at 1 MHz, while the MFM data-rate
// byte window remains 64 ticks (32 us). Media access then waits for HLT.
// DRQ service resets the byte timer.
// A Write Track preload waits for a rising index event and does not age here.
void wd179x_tick(wd179x* fdc, unsigned ticks);
uint8_t wd179x_read(wd179x* fdc, uint8_t reg);
void wd179x_write(wd179x* fdc, uint8_t reg, uint8_t data);

#endif
