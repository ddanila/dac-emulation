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
