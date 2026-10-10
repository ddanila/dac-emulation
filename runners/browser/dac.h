#ifndef DAC_BROWSER_H
#define DAC_BROWSER_H
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
#endif
