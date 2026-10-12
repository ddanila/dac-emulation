# Drive timing and visualization

The controller, drive mechanics, browser geometry and seek sounds now share one
emulated clock. This is a deterministic reference model, not a claim that the
owner's unmeasured drives have identical mechanical dynamics.

## Controller behavior

- Read-ID waits for the next physical ID in the selected track's rotational order.
  It does not increment the last sector number and return immediately.
- Data commands search physical tracks for matching C/H/R/N. Logical cylinder and
  head IDs are separate from physical head position/side. Missing IDs terminate
  after two index crossings; missing marks, wrong-cylinder and DSK CRC/control-mark
  flags are distinguished. SK skips deleted sectors during normal reads.
- Each drive has independent phase and an index pulse (nominal 2.5 ms width).
  At full speed a revolution is 798720 CPU clocks at 3.9936 MHz (300 RPM).
- Byte cadence uses the rational 250 kbit/s rate: event k occurs at
  `origin + ceil(k * 79872 / 625)` clocks. Servicing a byte late does not shift
  subsequent byte times. Missing its 26 μs service window reports ST1 overrun.
- Motor off removes READY and aborts active execution with ST0 Not Ready. Commands
  issued before READY also report Not Ready; they no longer wait forever.
- SPECIFY programs step interval and head load/unload timers. Seek pulses update
  physical position separately from the controller's present-cylinder counter.
  Physical travel stops at cylinders 0 and 79; the logical counter may run farther.
  RECALIBRATE stops at track zero or after 77 pulses and reports equipment check
  if zero was not reached. A second recalibration can finish from track 78/79.

Reference: [NEC μPD765 datasheet](https://hxc2001.com/download/datasheet/floppy/thirdparty/FDC/NEC/765.pdf).
The [Wang PC technical reference, floppy controller chapter](https://www.bitsavers.org/pdf/wang/professional_computer/TechRefMan-1985.pdf)
also describes the need for two recalibrations on an 80-track drive.

## Mechanical reference profile

[TEAC FD-55FV-13 specification](https://retrocmp.de/fdd/teac/TEAC_FD55-FV.pdf),
pp.107–109 and 120, supplies the nominal speed, track pitch, timing bounds and
READY conditions. The owner's exact FD-55 suffix/strap configuration is unverified.

| Property | Implemented profile | Evidence/assumption |
|---|---|---|
| Track pitch | 25.4/96 mm; 20.902083 mm across 79 steps | Documented 96 tpi |
| Startup | Linear speed ramp over 400 ms | Duration uses the documented bound; curve is assumed |
| Coast-down | Linear ramp over 400 ms | Assumed; no specimen measurement |
| READY | Motor command on, media present, two index crossings after half speed, latest interval within ±6% | Documented reference conditions; immediate READY removal on motor off is within the stated bound |
| Head movement | Linear 3 ms transition per STEP, starting from the current interpolated position | Reference minimum track-to-track time; trajectory is assumed |
| Settling | Data search waits 15 ms after the movement interval | Conservative documented upper bound |
| Head loading | Waits the greater of SPECIFY HLT and 50 ms after load | Reference bound; exact straps are unknown |
| Unloading | SPECIFY HUT after a result, or motor off | Deterministic control profile |

All ramp, movement, search, index and byte-deadline state participates in snapshots
and replay. The browser samples the core's fractional head position and spindle
phase without wall-clock extrapolation. At accelerated speed, several steps may
occur between frames. Reduced motion deliberately freezes the rotor display.
The separate mechanical demo remains an illustration and never commands the FDC.

A 64-event ring per drive records STEP timestamps. Optional synthesized clicks
use those events, including multiple steps between frames, scaled to the selected
emulation speed. Reset, hidden-tab and stale batches are discarded rather than
played in a burst. Motor tone follows the modeled speed. Timbre is not a recording
of the specimen.

## Disk layout

Raw 819200-byte images remain supported with an explicitly inferred MFM layout:
80 cylinders, two sides, five 1024-byte sectors in order 1–5, GAP3 27. ID and data
positions derive from a conventional MFM track layout (162 bytes to first CHRN,
44 more to data, 1086+GAP3 bytes per sector), rather than evenly spaced sector
numbers. These are reference positions, not recovered flux measurements.

[Standard DSK](https://cpctech.cpcwiki.de/docs/dsk.html) and
[extended DSK](https://cpctech.cpcwiki.de/docs/extdsk.html) are accepted directly by
both browser drives and the native runner. Supported images have 80 cylinders,
two sides, at most five 1024-byte sectors per track, and a 250 kbit/s MFM-compatible
layout. ID order, CHRN, GAP3 and supported error flags are preserved. Extended DSK
may contain unallocated tracks. Oversized, truncated, unsupported-density,
variable/weak-sector and out-of-capacity layouts are rejected, not flattened.
The limit is 1 MiB per image.

DSK reads/writes address the original sector payloads. Formatting an allocated
five-sector DSK track retains the submitted ID order and GAP3 in its header, so
export, remount, library copies and snapshots preserve them. Track reallocation
and other sector sizes are not supported. Raw formatting accepts canonical order
only: use DSK when interleave must survive export. Disk exports keep `.dsk` for a
DSK container; raw exports remain `.img`. The default historical image stays raw
so existing media identities and saved sessions remain usable.

The optional libdsk tool `tools/robotron_td0_to_dsk.c` preserves the ID order
reported by a TeleDisk image; it refuses read errors, unsupported tracks and
existing output paths. GAP3 0x54 is explicitly assumed, since TD0 does not supply
physical gap measurements. Example after installing libdsk:

```sh
cc -std=c11 tools/robotron_td0_to_dsk.c -ldsk -o /tmp/td0-to-dsk
/tmp/td0-to-dsk A92V010A.TD0 tosm10.dsk
```

The original TOS/M TD0 was converted and booted to `A>` during validation. Its
reported ID order was 1–5 on all 160 tracks; no interleave was invented.

## Remaining limits

There is no flux/PLL model, spindle jitter, measured angular alignment, mechanical
backlash, calibrated motor acoustics, or simulated failure from an excessively
fast STEP rate. Linear trajectories and conservative delays are approximations.
Index gating uses the reference profile, not measured specimen straps. Formatting
collects its ID tuples at byte cadence after index and updates an existing track;
it does not reproduce every write-gap interval or interrupted-format damage.
Partial writes on overrun are discarded rather than reproducing magnetic damage.
Read Track and Read/Write Deleted Data commands and other densities are not
implemented; supported DSK metadata does not imply general copy-protection support.

## Validation

Native tests cover startup/READY/coast, phase wrap, index-based ID search and
missing-sector termination, precise cadence, overruns, physical head movement,
77-pulse recalibration, DSK order, format persistence and malformed-image rejection.
WASM snapshots restore fractional position, ramp speed, phase and STEP timestamps
mid-seek with identical continuation. Browser checks cover event spacing, stale
sound suppression, fractional geometry, DSK insertion/snapshot/export, and
preserved older runtimes. Bounded historical OS checks cover directory/type,
create/copy/delete, reboot and write protection. No full Verilog run is required.
