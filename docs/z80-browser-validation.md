# Z80 and browser milestone validation

Updated 2026-10-10. Exact upstream commits and external-media SHA-256 identities are in [z80-provenance.json](z80-provenance.json). These results qualify bounded scenarios, not complete hardware fidelity.

- `make test`: independent instances, Z80-only indexed/bit instructions, HALT clock progression, Robotron bank separation, floppy read/write/write-protect/invalid-size/scan-equal behavior, and the existing Juku/media tests. Focus-loss release is checked through the Juku contact API.
- Vendored Z80 against pinned upstream chips-test: 75 instruction cases and 10 interrupt cases pass. `tests/differential/chips_upstream.py` reproduces these without importing another CPU implementation.
- Native machine and Robotron peripheral tests pass AddressSanitizer and UndefinedBehaviorSanitizer. Focused checks cover DMA ready polarity, memory copy, completion/readback, interrupt enable/control, whole/short-write TC, FDC reset/status, DMA/CTC priority and RETI, CRTC geometry, start/stop, field attributes and cursor.
- VJUGA: both native decode modes match the 6,000-write framebuffer oracle; no Verilog simulation required.
- Juku: all ten bounded legacy comparisons still match exactly after adding the interactive keyboard API.
- Robotron/TOS-M: cold boot, `DIR`, `TYPE AUTOEXC.SUB`, and writable-session `ERA AUTOEXC.BAK` followed by `DIR AUTOEXC.*` pass. Test fixtures confirm the original files remain unchanged. The original PIP failure was traced to the supplied raw disk, whose PIP differs in all ten sectors from the original TeleDisk image. Using a fresh decode, create/read/text-copy/binary-copy/reboot/delete and read-only checks pass; the 10 KB executable copy matches exactly and all original files survive unchanged. See the [media recovery instructions](../machines/robotron1715m/README.md#tosm-media-recovery-and-the-pip-failure).
- WASM: independent instances, all three diagnostic machine profiles, bounded slices, keyboard output, reset determinism, power-off pixels, and destruction pass under Node.
- Native and WASM original Robotron boot produce identical 640×288 RGBA bytes after 100,000,000 clocks (timed floppy model): SHA-256 `b29650103b6582b0c86eab8a03381f58347125d62790876fde47ec7068ec238a`.
- Native and WASM create/read/copy also produce identical complete session disks: SHA-256 `7dde1f1bbbe1ebbcc31e22996dbde174e06e3b0159abc406889613e639eee0bc`.
- Chromium museum checks: power, live pixels, keyboard, reset, view controls, machine switching, invalid-media rejection and recovery pass. Desktop/mobile layouts were inspected. A separate local-media browser run booted the original TOS/M and displayed `DIR` output.

Original-media checks are optional and require caller-supplied inputs:

```sh
python3 tests/integration/robotron_boot.py s550.bin cas.bin robotron.img --file-operations --report build/robotron.json
make build/browser-reference
node tests/integration/wasm_parity.mjs s550.bin cas.bin robotron.img --file-operations
```

No full HDL run, MAME runtime differential, exact physical-variant validation, detailed model qualification, Safari/Firefox test, or full application suite is claimed. Current machine-specific limitations are listed with each core. Firmware rights and physical evidence remain separate from the MIT software implementation.

Additional validation on 2026-10-10:

- Native focused tests: keyboard matrix bounds, single LED toggle per I/O strobe, tap/release; SIO 8N1 framing, FIFO overrun, receiver enable/reset and error reset; timed seek/busy/sense, absent drive and wrong-cylinder rejection.
- External S600: matrix A, Shift+A, Ctrl+A modifier packet, ET, SI/SO LED and error-free serial reception. A native TOS/M experiment entered DIR using physical matrix switches.
- The timed floppy model passes the full bounded native file-operation checks above, with byte-for-byte native/WASM disk parity. Boot and command allowances are longer in emulated time because transfers are paced.
- WASM: save/restore, deterministic continuation, corruption rejection without mutation, and a mid-boot historical snapshot resumed to the same framebuffer.
- Museum: firmware-driven 3D DIR, physical keyboard disk edit, disk survival across reload, saved-disk discard, and saved machine state across reload.

Fast default checks still need no external firmware or HDL. External S600 and TOS/M checks are optional. This pass does not rerun the earlier Juku/VJUGA/upstream CPU qualification or assert their results against additional hardware.
