#ifndef DAC_OBSERVE_H
#define DAC_OBSERVE_H
#include "session.h"
#include "../trace/trace.h"
const char *dac_runtime_build_id(void);
unsigned dac_verification_abi(void); /* observation/trace C layout, currently 1 */
/* Diagnostic observation, never guest bus accesses. Not a save-state format. */
enum { DAC_MEMORY_RAM = 1, DAC_MEMORY_ROM = 2, DAC_MEMORY_VIDEO = 3 };
typedef struct {
  uint64_t cycles;
  uint32_t pc, sp, halted, bank;
} dac_observation;
/* Returns -ENOTSUP for unimplemented observation, -EINVAL for bad bounds.
 * RAM is physical backing storage: Robotron bank N starts at N*65536.
 * ROM is the boot ROM. VIDEO is the machine's video backing bytes.
 * No I/O reads, refresh, trace events or other emulated side effects. */
int dac_observe(dac_session *, dac_observation *);
int dac_peek(dac_session *, unsigned space, uint32_t offset, void *, size_t);
/* Sink copied, user pointer borrowed. Retained across reset/state load;
 * observers and their counters are not part of guest snapshots. NULL detaches.
 * Juku and Robotron supported; VJUGA returns -ENOTSUP for a non-NULL sink. */
int dac_set_trace(dac_session *, const dac_trace_sink *);
#endif
