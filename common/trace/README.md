# Shared tracing

`trace.h` defines typed events (kind, address, data, cycle, source) and callback sinks with an optional event limit. The core performs no trace-file I/O. Native formatting remains in the compatibility runner so existing comparison artifacts stay identical.

Robotron now emits memory and interrupt acknowledgements as well as I/O,
with CPU/DMA master and resolved backing-space offsets. Juku's existing event
order and text format remain unchanged; its mapped-space field is unknown.
See [verification](../../docs/verification.md) for strict comparison modes and
the distinction between access-order and physical timing claims.
