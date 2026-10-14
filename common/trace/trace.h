#ifndef DAC_TRACE_H
#define DAC_TRACE_H
#include <stddef.h>
#include <stdint.h>

enum { DAC_MASTER_CPU = 0, DAC_MASTER_DMA = 1 };
enum { DAC_SPACE_UNKNOWN = 0, DAC_SPACE_RAM = 1, DAC_SPACE_ROM = 2,
       DAC_SPACE_VIDEO = 3, DAC_SPACE_GLYPHS = 4, DAC_SPACE_IO = 5 };
typedef struct {
  const char *kind; /* MR, MW, IR, IW, IA; borrowed for the callback */
  uint32_t address;
  uint8_t data;
  uint64_t cycle;
  unsigned source; /* machine identity: Juku=0, Robotron=2 */
  unsigned master; /* CPU or DMA, independent of machine identity */
  unsigned space;  /* UNKNOWN means no mapped-address assertion is available */
  uint32_t offset; /* byte offset within backing space, not CPU address */
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
void dac_trace_emit_event(dac_trace_sink *, const dac_trace_event *);
void dac_trace_access(dac_trace_sink *, const char *, uint32_t, uint8_t,
                      uint64_t, unsigned, unsigned, unsigned, uint32_t);
#endif
