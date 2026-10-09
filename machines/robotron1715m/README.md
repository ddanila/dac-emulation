# Robotron 1715M / PC-1715W functional profile

This is an experimental portable C machine using the shared Z80 adapter. Its tested profile is the S550 boot ROM, 287 CAS PROM and TOS/M 1.0 raw disk. It cold-boots to `A>`, accepts keyboard packets, lists a directory, reads a text file and deletes a file on a session copy. No guest ROM patches or guest-PC traps are used. Matching Danila's exact physical machine is still pending.

Implemented: 256 KB RAM with independent read/write banks selected through the supplied CAS PROM; boot ROM/gap/character/video windows; a functional CTC timer cascade; SIO keyboard receive registers with K7658 packets; the boot-path DMA programming and interrupt protocol; raw 80×2×5×1024 media; floppy specify/sense/recalibrate/seek/read-ID/read/write/scan commands. Storage uses `common/media`. Native I/O events can use `common/trace`.

Build `make`, then:

```sh
build/robotron-boot /path/s550.bin /path/cas.bin /path/robotron.img 40000000 $'DIR\r'
```

The optional last argument `--writable` enables only an in-memory disk copy. Input files are never changed. `DAC_TRACE_IO=1` logs I/O writes. Convert an external CAS hex file with `python3 tools/prepare_robotron_media.py 287.hex cas.bin`. ROMs and disks are neither bundled nor licensed by this repository.

## Known limits

- This is a functional emulator, not a cycle-accurate board reconstruction. DMA transfer timing, terminal-count edges, floppy rotation/seeking, ready/reset lines and CTC trigger/daisy-chain details need further verification.
- Only one drive and one explicit raw geometry are supported. Sector error/deleted-data metadata, formatting and many less-used FDC/DMA modes are unimplemented.
- The browser uses a fixed 80×24, 8×16 character raster; full 8275 field attributes, cursor, scan timing and light-pen behavior are not modeled. The supplied character RAM is used, including glyphs loaded by the OS.
- Keyboard input uses K7658 packets based on the reference host; it does not run the keyboard's MCU ROM. Complete physical key mapping, SIO serial clocks/interrupts, printer and V.24 are pending.
- `PIP DAC.SUB=AUTOEXC.SUB` currently returns without creating the file. General application/file-copy compatibility is not qualified. `DIR`, `TYPE AUTOEXC.SUB`, and `ERA AUTOEXC.BAK` have separate passing checks.
- No MAME execution differential or physical-machine comparison has been performed. Source comparison and successful boots do not prove hardware accuracy.

See [source identities](../../docs/z80-provenance.json), [validation](../../docs/z80-browser-validation.md) and `REFERENCE_LICENSE`. Original DAC code is MIT; reference attributions are preserved in `NOTICE`.
