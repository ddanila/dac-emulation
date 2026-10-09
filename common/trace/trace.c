#include "trace.h"
void dac_trace_emit(dac_trace_sink *sink, const char *kind, uint32_t address,
                    uint8_t data, uint64_t cycle, unsigned source) {
  if (!sink || !sink->emit || (sink->limit && sink->count >= sink->limit)) return;
  dac_trace_event event = {kind, address, data, cycle, source};
  sink->count++;
  sink->emit(sink->user, &event);
}
