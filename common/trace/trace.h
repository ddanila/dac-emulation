#ifndef DAC_TRACE_H
#define DAC_TRACE_H
#include <stddef.h>
#include <stdint.h>

typedef struct {
  const char *kind; /* MR, MW, IR, IW, IA; borrowed for the callback */
  uint32_t address;
  uint8_t data;
  uint64_t cycle;
  unsigned source;
} dac_trace_event;
typedef void (*dac_trace_callback)(void *, const dac_trace_event *);
typedef struct {
  dac_trace_callback emit;
  void *user;
  uint64_t count;
  uint64_t limit; /* zero = unlimited */
} dac_trace_sink;
void dac_trace_emit(dac_trace_sink *, const char *, uint32_t, uint8_t,
                    uint64_t, unsigned);
#endif
