# Juku E5104

The extracted core owns CPU, RAM, devices, interrupt, keyboard, and video state per instance. `juku.h` exposes creation/destruction, ROM loading, bounded execution, and a borrowed monochrome video buffer. `juku_internal.h` supports the compatibility runner and tests; it is not a stable public ABI.

Host hooks supply serial transport, diagnostics, and observation. Files, PTYs, environment variables, signals, and pacing belong to the native runner. ROM loading in the core does not apply the legacy runner's checksum patch.

Execution remains instruction-granular. The shared runtime advances halted time so clocked devices and interrupts continue. Diagnostic checkpoints are not complete restorable save states. The shared runtime supplies browser input, reset/power lifecycle and versioned restorable states.

See [provenance and validation](../../docs/juku-extraction.md).

Physical keyboard and text-contact APIs share independently owned contacts.
See [keyboard qualification](../../verification/juku-keyboards/README.md) for
Juku/JUSS/AT layouts, repeat timing, snapshot state and model boundaries.
