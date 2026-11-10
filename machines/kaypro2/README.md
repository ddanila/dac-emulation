# Kaypro II / 2 — 81-240A serial bring-up

Native headless board core at 2,500,000 Hz. This targets inventory PC003's
reported PC81-240A, 4 KiB 81-232 boot EPROM and MK3884N SIO. It is not the
1984 universal-board Kaypro 2. No historical ROM is distributed.

Implemented: shared tick-driven Z80, 64 KiB RAM, switchable lower 16 KiB,
4 KiB ROM at 0000–0FFF, 2 KiB physical video RAM behind the window at 3000–3FFF, system PIO bank latch,
8116 baud selectors, two polling SIO channels with three-byte receive FIFO,
error reset, two-stage timed transmission, and mapped memory/I/O tracing.
The serial receive API represents a completed byte. Its caller must pace
arrivals; the core never queues an unlimited stream behind the guest FIFO.

ROM-selected writes below 3000 do not reach RAM. Reset selects ROM/video;
bit 7 of system PIO A at 1C selects the bank (one = ROM/video). A serial
bootstrap must relocate above 3FFF before clearing that bit. The ROM is not
copied beneath itself as on the ordinary Robotron.

The timing and SIO register model is adapted from the existing Robotron
`peripherals.h` implementation; the Z80 and tracing code are shared directly.
SIO interrupts, modem transitions, bit-level framing/error injection, floppy
controller, keyboard MCU firmware, CRT sync waveforms and PIO handshakes are
not implemented. The deterministic renderer produces 560×240 monochrome pixels
from a caller-supplied 2048-byte character ROM and explicit blink phase.
This is a schematic-derived display model, not physical qualification. Unmapped ROM-space
reads return FF as an explicit open-bus approximation. No browser/runtime
kind is registered yet; use the native C API and the CP/M integration probe.
Do not treat this as a complete stock-ROM/floppy emulator.

## Source cross-check (2026-11-10)

Primary board sources:

- [NLS 81-241 sheet 2A, CPU and memory](https://retrocmp.de/kaypro/Kaypro-II-4_83_81-241_Schematics_1983-01-05_1983-01-12_CPU.pdf):
  U63 clock from 20 MHz / 8; U47 2716/J1 or 2732/J2; U60 ROM/CRT decode;
  U39 main-RAM RAS gating. Inspect the actual 2732 configuration, not the
  early 81-110's 2 KiB ROM description.
- [Kaypro technical manual 1484-E](https://retrocmp.de/kaypro/1985_1484-E_KayproTechnicalManual.pdf),
  printed 6-13 through 6-15 (PDF pages 33–35): sheet 2B connects U78 FT to
  SIO A RX/TX clocks, FR to channel B, A to J4 RS-232 and B to the keyboard;
  system PIO A7 is BANK, A6 controls the active-low motor signal, A3 is busy.
  Sheet 2C describes discrete video logic, not a 6845.
- [Mostek 1981 data book](https://manuals.plus/m/6bb07f80edc1761aa95a1e4bcdf3fecdc19103dc646a6960e4872c97a77da43a):
  MK3884 register selection/reset, asynchronous framing and FIFO semantics.

Independent implementation consulted:
[MAME kaypro.cpp](https://github.com/mamedev/mame/blob/master/src/mame/kaypro/kaypro.cpp)
and [kaypro_m.cpp](https://github.com/mamedev/mame/blob/master/src/mame/kaypro/kaypro_m.cpp),
BSD-3-Clause, Robbbert and contributors. No MAME code is copied. Map agrees on
SIO data A/B = 04/05 and control A/B = 06/07, baud A = 00–03 and B = 0C–0F,
system PIO A data/control = 1C/1D. MAME also inhibits writes under ROM and
starts in ROM/video bank. Its simplified 4 KiB video window is not evidence
of 4 KiB physical video RAM. U57's schematic ignores A5/A6; these I/O aliases
are covered in this core even though MAME's map lists only base ranges.

Qualification is split: native unit tests verify memory isolation, decoding,
FIFO/timing and reset; cpm-plus-kaypro exercises real guest instructions with
production host-disk services. Its optional MAME test independently executes
the same replacement ROM through relocation, PIO banking and the RX wait.
Neither test is physical acceptance of PC003.

## Physical video packing

Sheet 2C, U16 selects on CPU A6 (column 64). Its A inputs are A4, A5,
A10, A11; its B inputs are A10, A11, 1, 1. Outputs drive SRAM A4, A5,
A9 and the complementary byte-pair enables. CPU A7–A9 feed SRAM A6–A8.
Consequently, with `a` the offset in the logical aperture:

```
A6 clear: (a & 0x3f) | ((a >> 1) & 0x7c0)
A6 set:   0x600 | (a & 0x0f) | ((a >> 6) & 0x30) | ((a >> 1) & 0x1c0)
```

The visible 24×80 cells are all distinct. Columns 80–127 alias columns
64–79 within a row. Rows outside the visible region can overlap visible
cells. Tests cover the 1920 distinct cells and representative aliases.
MAME's flat window is consulted for visible layout, not these aliases.

The renderer follows U43's five connected pixel outputs, seven-pixel cell
width, ten scanlines per cell and blink selection. Synthetic test glyphs
are explicitly identified; no stock or PC003 character-ROM image is included.
Channel B uses the same three-byte FIFO API as A. The CP/M qualification probe
injects completed keyboard bytes on an independent 300-baud 8N1 schedule;
its report distinguishes receiver rejection from software queue overflow.
