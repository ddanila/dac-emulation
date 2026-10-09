# Juku extraction

Source: `ddanila/8080-cosim` at `8e74542e3f6a255c20c709156ae09ecb7fe750b8`, fetched before extraction. The source's `juku-common` submodule is `43ecf323a9c9bd13902f8558bf428b91b09abc95`. The related CP/M repositories were also fast-forwarded before validation.

Commit `8b2d841` records the original source bytes before refactoring. [juku-source.json](juku-source.json) records paths and SHA-256 hashes. The original Juku work is by Danila Sukharev; the CPU retains Nicolas Allemand's MIT notice. See [NOTICE](../NOTICE) for the MAME reference attribution.

## Changes

- Machine globals became instance-owned state in `machines/juku`; CPU callbacks carry the instance explicitly.
- Shared trace sinks and parameterized callback-backed media live in `common`. Juku's disk geometry and deleted-sector metadata stay in its adapter.
- Native filesystem, terminal, environment, signal, pacing, and diagnostic formatting code stays in `runners/native`. The core can use memory-backed disks.
- The unchanged 8080 CPU is vendored with its original license. No new CPU, hardware behavior, or firmware is introduced.

The public API is experimental. Internal state remains visible to the compatibility runner for instrumentation. Execution is instruction-granular, halted clock advancement is incomplete, and checkpoints are diagnostic snapshots rather than complete save states. WebAssembly integration and the full museum input/power interface are not implemented.

VJUGA is already an existing Z80 hardware implementation with adapted firmware. Its optional tv80 comparison harness is retained here; this does not turn the 8080 library into a general Z80 emulator. VJUGA and Robotron should share a future software Z80 dependency with distinct memory maps and peripherals.

## Validation recorded during extraction

Fast default: `make test` (no firmware, PTY, or HDL). The support suite also passes AddressSanitizer and UndefinedBehaviorSanitizer on macOS. Passed strict C builds and support tests on macOS and Linux/aarch64. Tests exercise independent interleaved instances, ROM loading, bounded halted execution, video access, trace limits, media geometry/bounds/write policy, and memory-backed disk attachment.

Additional checks already run:

- Ten original-versus-extracted C scenarios match byte for byte: RAM/state, framebuffer, typed bus/read traces, stdout and stderr. Includes all available monitor ROMs, keyboard, disk boot and injected CPU/RAM faults.
- Original CPU conformance: 4,480,153 assertions; original disk, FDC, PIT/latch, checkpoint, pacing and ROMBIOS read/write/console fixtures pass on macOS and Linux.
- Serial overrun/PIT boundary tests pass on both platforms. Linux interactive console test passes.
- CP/M Plus `network-smoke` passes with `JUKU_COSIM_TRACE` pointing to the extracted runner: prompt, DIR, TYPE, DIAG CPU, WBOOT and ERA; 53 reads, one write, no retries or overruns.
- Optional CPU HDL differential passed 8,192 vectors; FDC differential passed 12 seeds / 50,845 transitions.

Outstanding coverage and inherited failures:

- Automatic PTY regression fails with both the untouched baseline and extracted runner (PTY closure on macOS, timeout on Linux). This is not claimed as passing serial qualification.
- Full structural Juku HDL cannot elaborate the pinned source: unresolved `pit_hchain`, `pit_vchain`, `hor_rtr`, and `d94_d1_d99_a2n` in `hdl/juku_top.v`. The extracted C does not modify that RTL. Full bus/INTA comparison remains unqualified.
- The VJUGA tv80 boot run was stopped to keep intermediate work fast. The optional script has not completed qualification.

Full Verilog runs are opt-in, not intermediate checks. Existing consumers remain on their original code. Switching `8080-cosim` to this library is the next migration step after reviewing these qualification gaps; the duplicate source is a temporary migration state.

## Reproduce bounded native comparison

From this repository, with the pinned source available at `../8080-cosim`:

```sh
make -j4 test
cc -O2 -I../8080-cosim/cosim ../8080-cosim/cosim/trace.c \
  ../8080-cosim/cosim/i8080.c ../8080-cosim/cosim/juk_disk.c \
  ../8080-cosim/cosim/juku_fdc.c -o build/juku-baseline
python3 tests/differential/legacy_compare.py ../8080-cosim \
  build/juku-baseline build/juku-trace --report build/comparison.json
```

For the optional inherited native fixtures, run `tests/integration/upstream_checks.py ../8080-cosim`. Add `--serial` or `--hdl` only when deliberately investigating those paths. Firmware and historical media stay in the reference checkout.
