# Juku E5104

The extracted core owns CPU, RAM, devices, interrupt, keyboard, and video state per instance. `juku.h` exposes creation/destruction, ROM loading, bounded execution, and a borrowed monochrome video buffer. `juku_internal.h` supports the compatibility runner and tests; it is not a stable public ABI.

Host hooks supply serial transport, diagnostics, and observation. Files, PTYs, environment variables, signals, and pacing belong to the native runner. ROM loading in the core does not apply the legacy runner's checksum patch.

Execution remains instruction-granular. A halted CPU that makes no progress returns early; elapsed halted time is not yet modeled. Diagnostic checkpoints are not complete restorable save states. Browser input, reset/power lifecycle, and a stable museum interface remain future work.

See [provenance and validation](../../docs/juku-extraction.md).
