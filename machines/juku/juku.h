#ifndef DAC_JUKU_H
#define DAC_JUKU_H
#include <stddef.h>
#include <stdint.h>
/* Portable core. Hardware profiles are public; diagnostic internals are not
 * a stable ABI. Firmware is always loaded without implicit patches. */
typedef struct juku juku;
enum { JUKU_PROFILE_COUNT = 7 };
typedef struct {
  const char *id, *name, *firmware;
  unsigned controller, card, keyboard; /* controller 1791/2/3; keyboard 0=Juku,1=JUSS,2=AT */
} juku_profile;
const juku_profile *juku_profile_info(unsigned);
int juku_set_profile(juku *, unsigned); /* before execution; negative errno */
unsigned juku_get_profile(const juku *);
juku *juku_create(void);
void juku_destroy(juku *);
/* Before execution only; copies up to 16 KiB and zero-fills the remainder.
 * Firmware checksums are preserved. */
int juku_load_rom(juku *, const void *, size_t);
/* Borrowed packed monochrome framebuffer, valid until destroy; contents and
 * dimensions may change on subsequent steps. Height is bounded by the
 * remaining RAM; use juku_frame for the acquired display. */
const uint8_t *juku_video(juku *, unsigned *stride, unsigned *lines);
/* Last completed packed monochrome scanout, NULL until the first frame.
 * Borrowed until the next frame publication/reset/destroy. */
const uint8_t *juku_frame(juku *, unsigned *stride, unsigned *lines, uint64_t *sequence);
/* Interactive single-contact keyboard; key=0, down=0 releases all. */
/* ASCII/synthetic keys, plus Latin-1 identities for äõöüÄÕÖÜ. These select
 * physical contacts or AT scan codes; the active ROM supplies guest bytes. */
void juku_key(juku *, uint8_t key, int down);
void juku_step(juku *);
/* Stops at instruction boundaries: may exceed budget by the last instruction
 * and interrupt entry effects. Returns actual CPU cycles advanced. A halted
 * CPU advances idle time when a timer is armed; without a clocked device it
 * returns early. Guest bus accesses remain instruction-granular. */
unsigned long juku_run(juku *, unsigned long budget);
/* Split stepping is for native instrumentation between CPU and device steps. */
void juku_step_cpu(juku *);
void juku_step_devices(juku *);
#endif
