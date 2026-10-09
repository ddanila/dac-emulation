# Shared tracing

`trace.h` defines typed events (kind, address, data, cycle, source) and callback sinks with an optional event limit. The core performs no trace-file I/O. Native formatting remains in the compatibility runner so existing comparison artifacts stay identical.
