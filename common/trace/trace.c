#include "trace.h"
void dac_trace_emit_event(dac_trace_sink *sink, const dac_trace_event *event) {
  if (!sink || !sink->emit || (sink->limit && sink->count >= sink->limit)) return;
  sink->count++;
  sink->emit(sink->user, event);
}
void dac_trace_access(dac_trace_sink *sink, const char *kind, uint32_t address,
                      uint8_t data, uint64_t cycle, unsigned source,
                      unsigned master, unsigned space, uint32_t offset) {
  dac_trace_event event = {kind, address, data, cycle, source, master, space, offset};
  dac_trace_emit_event(sink, &event);
}
void dac_trace_emit(dac_trace_sink *sink, const char *kind, uint32_t address,
                    uint8_t data, uint64_t cycle, unsigned source) {
  dac_trace_access(sink, kind, address, data, cycle, source,
                   DAC_MASTER_CPU, DAC_SPACE_UNKNOWN, 0);
}
