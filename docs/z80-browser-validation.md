# Z80 and browser milestone validation

Validated 2026-10-09. Exact upstream commits and external-media SHA-256 identities are in [z80-provenance.json](z80-provenance.json). These results qualify bounded scenarios, not complete hardware fidelity.

- `make test`: independent instances, Z80-only indexed/bit instructions, HALT clock progression, Robotron bank separation, floppy read/write/write-protect/invalid-size/scan-equal behavior, and the existing Juku/media tests. Focus-loss release is checked through the Juku contact API.
- Vendored Z80 against pinned upstream chips-test: 75 instruction cases and 10 interrupt cases pass. `tests/differential/chips_upstream.py` reproduces these without importing another CPU implementation.
- Native machine tests pass AddressSanitizer and UndefinedBehaviorSanitizer.
- VJUGA: both native decode modes match the 6,000-write framebuffer oracle; no Verilog simulation required.
- Juku: all ten bounded legacy comparisons still match exactly after adding the interactive keyboard API.
- Robotron/TOS-M: cold boot, `DIR`, `TYPE AUTOEXC.SUB`, and writable-session `ERA AUTOEXC.BAK` followed by `DIR AUTOEXC.*` pass. Test fixtures confirm the original files remain unchanged. `PIP` file-copy remains an open failure.
- WASM: independent instances, all three diagnostic machine profiles, bounded slices, keyboard output, reset determinism, power-off pixels, and destruction pass under Node.
- Native and WASM original Robotron boot produce identical 640×384 RGBA bytes after 40,000,000 clocks: SHA-256 `12e2706a2c35d8e209f1e483b933bafd52b8f0854310b06db4ce671f6deb6c6c`.
- Chromium museum checks: power, live pixels, keyboard, reset, view controls, machine switching, invalid-media rejection and recovery pass. Desktop/mobile layouts were inspected. A separate local-media browser run booted the original TOS/M and displayed `DIR` output.

Original-media checks are optional and require caller-supplied inputs:

```sh
python3 tests/integration/robotron_boot.py s550.bin cas.bin robotron.img --report build/robotron.json
make build/browser-reference
node tests/integration/wasm_parity.mjs s550.bin cas.bin robotron.img
```

No full HDL run, MAME runtime differential, exact physical-variant validation, detailed model qualification, Safari/Firefox test, or full application suite is claimed. Current machine-specific limitations are listed with each core. Firmware rights and physical evidence remain separate from the MIT software implementation.
