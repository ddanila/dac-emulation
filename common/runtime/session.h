#ifndef DAC_SESSION_H
#define DAC_SESSION_H
#include <stddef.h>
#include <stdint.h>
typedef struct dac_session dac_session;
/* kinds: 0=Juku, 1=VJUGA Rev-A Mode B, 2=Robotron functional profile.
 * Firmware slots: 0=boot ROM, 1=Robotron CAS PROM, 2=Robotron character data,
 * 3=Robotron keyboard firmware (optional S600, 2048 bytes).
 * All loads copy bytes. Persistence is owned by the host. */
dac_session *dac_create(unsigned kind);
void dac_destroy(dac_session *);
int dac_load(dac_session *, unsigned slot, const void *, size_t);
int dac_mount(dac_session *, const void *, size_t, int writable);
/* Robotron units 0/1, Juku unit 0. Empty bytes eject. No active transfers. */
int dac_mount_unit(dac_session *, unsigned, const void *, size_t, int);
const uint8_t *dac_disk_data_unit(dac_session *, unsigned);
unsigned dac_disk_size_unit(dac_session *, unsigned);
int dac_drive_inserted(dac_session *, unsigned unit, unsigned inserted);
/* Change a removed Robotron disk's notch protection without remount/reset. */
int dac_drive_protect(dac_session *, unsigned unit, unsigned protect);
int dac_drive_transfer(dac_session *, unsigned from, unsigned to);
int dac_drive_door(dac_session *, unsigned unit, unsigned open);
unsigned dac_drive_status_unit(dac_session *, unsigned);
/* Phase [0,798720), monotonically wrapping step count, active CHRN metadata.
 * Detail: bit 0 selected, 1 execution, 2 write, 3 seek; side bit 4;
 * sector bits 8..15. Returns zero for unavailable units/machines. */
unsigned dac_drive_phase_unit(dac_session *, unsigned);
unsigned dac_drive_steps_unit(dac_session *, unsigned);
unsigned dac_drive_detail_unit(dac_session *, unsigned);
unsigned dac_drive_position_unit(dac_session *, unsigned); /* cylinder Q16 */
/* ready, loaded, settling, index in bits 0..3; speed per mille in bits 8..17 */
unsigned dac_drive_mechanics_unit(dac_session *, unsigned);
/* Most recent STEP ages in CPU clocks, newest first; UINT32_MAX if absent. */
unsigned dac_drive_step_age(dac_session *, unsigned, unsigned);
/* Diagnostics: 0 cumulative indexes; 1 head load Q16; 2 controller phase
 * bits0..1, search bits4..6, command bits8..15; 3 byte position/length uint16;
 * 4 seven-byte result valid bit24 and ST0/ST1/ST2 bytes (only in result phase).
 * Returns zero when unavailable. */
unsigned dac_drive_diagnostic(dac_session *, unsigned unit, unsigned field);
const uint8_t *dac_printer_data(dac_session *);
unsigned dac_printer_size(dac_session *);
unsigned dac_printer_overflow(dac_session *);
void dac_printer_clear(dac_session *);
/* V.24 adaptive peer, shared CTC0 channel1 clock. Signals: CTS=1,DCD=2,
 * peer obeys guest RTS=4. Byte enqueue returns 0 or negative errno. */
int dac_serial_send(dac_session *, unsigned byte);
int dac_serial_signals(dac_session *, unsigned signals);
unsigned
dac_serial_status(dac_session *); /* flags0..2, queue count bits8..24 */
const uint8_t *dac_serial_data(dac_session *);
unsigned dac_serial_size(dac_session *);
unsigned dac_serial_overflow(dac_session *);
void dac_serial_clear(dac_session *);
int dac_cables(dac_session *, unsigned disconnected);
unsigned dac_cable_status(dac_session *);
int dac_power(dac_session *, int on);
int dac_reset(dac_session *);
unsigned dac_run(dac_session *, unsigned ticks);
int dac_key(dac_session *, unsigned key, int down);
unsigned dac_width(dac_session *);
unsigned dac_height(dac_session *);
const uint32_t *dac_video(dac_session *);
const uint8_t *dac_disk_data(dac_session *);
unsigned dac_disk_size(dac_session *);
unsigned dac_disk_activity(dac_session *);
int dac_matrix(dac_session *, unsigned key, int down);
int dac_tap(dac_session *, unsigned key, unsigned modifiers);
unsigned dac_keyboard_leds(dac_session *);
unsigned dac_drive_status(dac_session *);
unsigned dac_state_size(dac_session *);
int dac_state_save(dac_session *, void *, size_t);
int dac_state_load(dac_session *, const void *, size_t);

/* Incoming virtual peer; baud=0 follows guest framing. */
int dac_serial_peer(dac_session *, unsigned baud, unsigned format);
unsigned dac_serial_peer_baud(dac_session *);
unsigned dac_serial_peer_format(dac_session *);
const uint8_t *dac_serial_decoded_data(dac_session *);
unsigned dac_serial_decoded_size(dac_session *);
unsigned dac_serial_decoded_errors(dac_session *);
unsigned dac_serial_errors(dac_session *);
void dac_serial_cancel(dac_session *);
void dac_timeline_capture(dac_session *, unsigned);
unsigned dac_timeline_count(dac_session *);
const uint32_t *dac_timeline_data(dac_session *);
unsigned dac_circuit_activity(dac_session *, unsigned field);

#endif
