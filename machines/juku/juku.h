#ifndef DAC_JUKU_H
#define DAC_JUKU_H
#include <stddef.h>
#include <stdint.h>
/* Experimental portable core. Configuration is currently available through
 * juku_internal.h for the legacy harness; not yet a frozen museum ABI. */
typedef struct juku juku;
juku *juku_create(void);
void juku_destroy(juku *);
/* Before execution only; copies up to 16 KiB and zero-fills the remainder.
 * Unlike the legacy CLI, this does not patch firmware checksums. */
int juku_load_rom(juku *, const void *, size_t);
/* Borrowed packed monochrome framebuffer, valid until destroy; contents and
 * dimensions may change on subsequent steps. */
const uint8_t *juku_video(juku *, unsigned *stride, unsigned *lines);
/* Interactive single-contact keyboard; key=0, down=0 releases all. */
void juku_key(juku *, uint8_t key, int down);
void juku_step(juku *);
/* Stops at instruction boundaries: may exceed budget by the last instruction
 * and interrupt entry effects. Returns actual CPU cycles advanced. A halted
 * CPU with no progress returns early; advancing halted clock time is not yet
 * modeled by the inherited instruction-granular core. */
unsigned long juku_run(juku *, unsigned long budget);
/* Split stepping is for native instrumentation between CPU and device steps. */
void juku_step_cpu(juku *);
void juku_step_devices(juku *);
#endif
