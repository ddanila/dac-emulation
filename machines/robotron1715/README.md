# Ordinary Robotron PC 1715 — headless motherboard bring-up

This is a distinct machine from `robotron1715m` (the W/M profile). Runtime kind
**3**, verification name **robotron1715**, nominal clock **2,458,000 Hz**.
It is intended to host the [Pico1715](https://github.com/ddanila/Pico1715)
external-controller model without substituting an 8272 or changing the guest ROM.

Implemented:

- Shared Z80 CPU, flat 64 KB RAM, 2 KB boot-ROM read overlay at 0000h–07FFh.
- Writes reach underlying RAM while the ROM is visible. OUT 28h–2Bh disables
  the overlay regardless of data or upper address byte. Reset restores it.
- Bounded native execution, mapped memory trace and full-address I/O trace
  (source 3). Memory events retain the shared per-tick convention; I/O and
  interrupt acknowledge callbacks fire once per cycle, not once per held tick.
- Native external-device callbacks: I/O reads/writes, clock tick, IRQ,
  acknowledge, RETI and reset. No W/M CAS PROM or DMA controller is present.
- Shared session creation, slot-0 ROM loading, run/reset, observation and peek.

**Not implemented:** onboard CTC, SIO, keyboard, display/CRT, the two PIOs and
custom floppy controller, /WAIT, external memory inhibition or bus mastering.
Unclaimed I/O reads return FFh. A bare profile therefore represents bring-up
without operational peripherals, not a bootable SCP machine. Callbacks are an
emulator seam, not an electrical simulation of every X2 wire. The future board
model must arbitrate onboard/expansion decoding as those devices are added.

No video or misleading screen is returned: runtime dimensions are zero and
`dac_video` returns NULL. Mounted disks and snapshots return `-ENOTSUP`; keyboard
input is unsupported. Existing W/M snapshot layouts and runtime kind 2 are
unchanged. This profile is not yet exposed as a museum UI exhibit.

## Run

```sh
make build/pc1715-probe test-pc1715
build/pc1715-probe /path/r1715bt.bin 10000000 /path/new-io-trace.txt
python3 tools/check_pc1715_rom.py /path/r1715bt.bin --report build/plain-rom.json
```

The probe reads exactly 2048 bytes, never changes the ROM and refuses an existing
trace output. Its JSON describes execution and explicitly reports that disk boot
is unsupported. The optional ROM check accepts the specifically identified ROM
below, checks progress through the startup/controller code and records hashes.
The normal `make test` uses only original synthetic programs, no historical ROMs.

## Attach a controller model

Native users may call `pc1715_attach` before executing the board, or include
`common/runtime/pc1715.h` and call `dac_pc1715_attach` on a powered-off kind-3
session. The host owns callback state. Power/reset calls the card reset handler;
session destruction does not free host state. The current attachment has no
snapshot ABI. Read callbacks return 1 to drive data or 0 to leave the bus unclaimed.
Writes are broadcast, including the motherboard's ROM-disable writes.

The core reset retains physical RAM. The shared runtime's `dac_reset` is a cold
power cycle, consistently with its other profiles, and clears it. Both restore
the ROM and reset the attached card. All callbacks must be non-reentrant.

## Evidence and limits

Primary sources: [ZRE index-2B schematic](https://www.sax.de/~zander/pc1715/pc_zres.pdf)
and [service manual](https://xepb.org/robotron/docs/pc_serv.pdf), sections 1.2 and 3.
The 64 KB/lower-2-KB overlay map is also cross-checked against the existing
BSD-3-Clause MAME `rt1715.cpp` reference credited in NOTICE. Decoder aliases and
physical timing still need board verification; no second CPU clock is inferred
from the W/M profile.

The local reference `r1715bt.bin` is 2048 bytes with SHA-256
`51cb80639b5667f2611da71ce7305061566cf3474bda7db6fc82709d08e46d01`.
Its cached Corti disassembly annotates the wait routine around 0402h–0421h.
This ROM is not asserted to be the owner's specimen and is not redistributed.
The initial 10-million-clock run ends at 0412h with ROM disabled and controller
port writes observed. Reaching that wait without a controller is expected; it
does not qualify floppy reads, OS boot or real hardware timing.

Next: model the ordinary controller's PIO handshake/status/data stream and
interrupts using independent expectations from the schematics and stock ROM/OS.
Then qualify boot/read/write/reboot, and add onboard peripherals/display rather
than borrowing the W/M memory and device map.
