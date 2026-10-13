# Browser runner / C ABI v0.1

`dac.h` exposes independent sessions, copied firmware/media, cold power-on/off, reset, bounded execution, key input, RGBA video and disk export. Machine kinds: Juku (0), VJUGA Rev-A Mode B (1), Robotron functional profile (2). Reset recreates machine state but preserves the session's disk copy. Destroy releases all session allocations. Firmware must be loaded while off.

Build using Emscripten 6.0.12:

```sh
bash runners/browser/build.sh
python3 tools/build_demo.py
node tests/integration/browser_smoke.mjs
```

`EMCC` may name an alternative compiler executable. The generated ES module and WASM need an HTTP server; no filesystem, network service, threads or cross-origin isolation are required. The museum worker owns the session, caps each call at 100,000 clocks, schedules against monotonic wall time, and transfers copied pixels. Loading historical media is local and explicit; exported disks are downloaded copies. There is no server upload or automatic persistence.

Pointers returned by video/disk getters are borrowed until destroy or a relevant mutation. Memory growth can invalidate JavaScript typed-array views; always read the module's current `HEAPU8` after a call. Video dimensions may change after drawing; query them after `dac_video`. Pixels are RGBA bytes on the supported little-endian native/WASM targets.

Juku input is currently one contact at a time; key zero/up clears it on focus loss. Its browser adapter advances halted time in four-clock increments so frame IRQs can resume the CPU. The legacy native runner is unchanged. Long-running Juku sessions across the WASM32 cycle-counter wrap are not qualified. VJUGA's bounded profile has no keyboard/disk. Robotron keys enqueue character packets; release-all clears queued packets.

The bundled demonstration ROMs and glyphs are original MIT DAC diagnostics built by `tools/build_demo.py`. They are clearly distinct from historical firmware.

Additive drive telemetry: `dac_drive_phase_unit` returns rotational phase in
CPU ticks (0–798719); divide by 798720 for a revolution. `dac_drive_steps_unit`
returns the wrapping uint32 seek-step count since controller reset.
`dac_drive_detail_unit` packs selected/execution/write/seeking in bits 0–3,
side in bit 4 and sector in bits 8–15. Phase and steps are serialized with the
machine; querying them has no side effects. See `dac.h` and the Robotron drive
fidelity document. UI code must feature-detect these exports for archived cores.

`dac_drive_position_unit` returns a fractional physical cylinder in Q16.
`dac_drive_mechanics_unit` exposes READY, loaded, settling and index flags plus
speed per mille (see `dac.h`). `dac_drive_step_age` returns up to 64 recent STEP
ages in CPU clocks, newest first, or UINT32_MAX when unavailable. These queries
are pure; snapshots include the underlying ramp, pose and timestamp state.
Robotron mounts validate raw or supported standard/extended DSK before replacing
existing media. Exports preserve the mounted container and its byte length.

`dac_drive_diagnostic(session, unit, field)` adds cumulative index counts,
head-load progress, controller command/phase/search, byte position/length and
sampled result registers. Its packed fields are documented in `dac.h`. These
queries are read-only; older modules can be feature-detected. Current snapshots
include pending Read Track searches, delayed write padding and in-progress format
sectors. They require a matching core build; DAC retains earlier runtimes.

## Drive levers (0.8.0)

`dac_drive_door(session, unit, open)` controls each Robotron drive independently.
Opening clears READY and head loading, interrupts an active transfer with NR
(preserving an already-written prefix), and suppresses media index pulses.
Closing requires fresh qualifying index pulses. Disk bytes remain mounted.
Status bit 5 reports the open lever even with power off. Mechanical lever state
survives power/reset and snapshots. Recording opcode 9 is `(unit, open)`.
Older snapshots require their preserved core because the device layout changed.

`dac_drive_inserted(session, unit, inserted)` requires an open lever. Ejection
retains the session image and its writes for reinsertion/export; READY and index
are suppressed. Opcode 10 records insertion state. A fresh mount resets ejection.
