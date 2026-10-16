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
  flags are distinguished. SK skips the opposite address-mark type for Read Data and Read Deleted Data.
- Each drive has independent phase and a media-gated index pulse (nominal 2.5 ms width).
  Empty-drive rotation does not increment the optical index counter.
  At full speed a revolution is 798720 CPU clocks at 3.9936 MHz (300 RPM).
- Byte cadence uses the rational 250 kbit/s rate: event k occurs at
  `origin + ceil(k * 79872 / 625)` clocks. Servicing a byte late does not shift
  subsequent byte times. Missing its 26 μs service window reports ST1 overrun. Writes clock zero padding to the end of the field before reporting the error; short terminal-count writes also finish padding on the emulated clock.
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

Read/Write Deleted Data preserve the deleted address mark in DSK. A matching
Read Deleted succeeds; a mismatched mark reports CM unless skipped. Write Deleted
on raw media is rejected with NW because raw export cannot retain the mark.
Read Track starts after index and reads data fields in physical order until the
EOT sector count or terminal count, accumulating CRC errors. It reports ND if no
command CHRN matched. This bounded implementation requires the requested N to match
each encountered sector; differing-size Read Track recovery is not implemented.
Normal sector commands can access mixed-size EDSK tracks.

Formatting accepts the allocated track's sector count and sizes, requests each
ID tuple at reference MFM positions, and clocks the filler/data interval before
committing that sector. Completed sectors survive a later underrun or interruption.
The sector currently being formatted remains unchanged if interrupted: this is a
sector-level approximation. Motor-off, controller reset and browser power-off
during a data write preserve the host-written prefix; DSK retains a bad data CRC
while raw cannot retain this metadata.

Compatible command behavior is also described in the manufacturer's
[Intel 82078 controller datasheet](https://bitsavers.computerhistory.org/components/intel/_dataSheets/82078_CHMOS_Single-Chip_Floppy_Disk_Controller_Jan94.pdf).
Reference layout positions determine request timing, not a recovered flux stream.

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
of the specimen. Muting, powering off or hiding the page cancels queued seek clicks.
The separate upper arm follows head-load progress; its 0.08-radian lift and pivot
are illustrative. A translucent exposed medium rotates with the hub; its stationary
jacket is omitted to keep mechanisms visible.

## Disk layout

Raw 819200-byte images remain supported with an explicitly inferred MFM layout:
80 cylinders, two sides, five 1024-byte sectors in order 1–5, GAP3 27. ID and data
positions derive from a conventional MFM track layout (162 bytes to first CHRN,
44 more to data, 1086+GAP3 bytes per sector), rather than evenly spaced sector
numbers. These are reference positions, not recovered flux measurements.

[Standard DSK](https://cpctech.cpcwiki.de/docs/dsk.html) and
[extended DSK](https://cpctech.cpcwiki.de/docs/extdsk.html) are accepted directly by
both browser drives and the native runner. Supported images have 1–80 cylinders,
1–2 sides, at most 29 sectors per track, N=0–5 (128–4096 bytes), and a
250 kbit/s MFM layout within 6250 bytes per revolution including gaps. Standard DSK
uses uniform track sector sizes; extended DSK permits mixed sizes. Unrepresented
physical cylinders/sides are unformatted, not mirrored. ID order, CHRN, GAP3 and supported error flags are preserved. Extended DSK
may contain unallocated tracks. Oversized, truncated, unsupported-density,
variable/weak-sector and out-of-capacity layouts are rejected, not flattened.
The limit is 1 MiB per image.

DSK reads/writes address the original sector payloads. Formatting an allocated
DSK track retains the submitted ID order and GAP3 in its header, so
export, remount, library copies and snapshots preserve them. Track reallocation
and changing the existing count/size allocation are not supported. N=0 commands
use DTL up to the 128-byte physical size. Raw formatting accepts canonical order
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
is progressive at whole-sector boundaries; it cannot represent a partially written
ID/gap. Interrupted data writes persist their prefix and a DSK CRC flag, without
reproducing every magnetic bit cell. Raw exports cannot retain error flags.
Read Track requires uniform command-matching sizes. Weak/random multiple-copy
payloads, FM/other densities and over-capacity tracks are explicitly rejected;
supported DSK metadata does not imply general copy-protection support. Measured
acoustic timbre and specimen trajectories still need recordings or captures.

## Validation

Native tests cover startup/READY/coast, phase wrap, index-based ID search and
missing-sector termination, precise cadence, overruns, physical head movement,
77-pulse recalibration, DSK order, format persistence and malformed-image rejection.
WASM snapshots restore fractional position, ramp speed, phase and STEP timestamps
mid-seek with identical continuation. Browser checks cover event spacing, stale
sound suppression, fractional geometry, DSK insertion/snapshot/export, and
preserved older runtimes. Bounded historical OS checks cover directory/type,
create/copy/delete, reboot and write protection. No full Verilog run is required.

Additional fixtures cover every supported N, mixed-size offsets, smaller single-side
images, deleted-mark round trips, Read Track order/index/CRC accumulation, timed
write underruns and interrupted formatting. The museum's bounded TOS/M regression
copies PIP.COM, restores a snapshot after DMA has written part of a sector, compares
8192 controller/mechanical samples at 64-clock intervals plus media bytes, then
independently decodes the final file. The diagnostic panel shows sampled controller
results only when valid; cumulative index counts expose pulses between frames.

## Read Track investigation and interruption coverage (0.13)

The [December 1978 NEC datasheet](https://bitsavers.trailing-edge.com/components/nec/_dataSheets/uPD765_Data_Sheet_Dec78.pdf),
printed p.14, specifies starting at index, continuing after CRC errors, CHRN
comparison and an EOT sector count. Its continuous-stream description does not
settle mixed-size transfer length/recovery for the sector-level DSK data available
here. No flux, gap payload or weak-bit data is present. Mixed-size Read Track
therefore remains explicitly unsupported; a size mismatch reports ND before any
out-of-sector read. This is an implementation limit, not a claim that the physical
controller rejects such media. Resolving it needs a more specific controller
reference or hardware trace and an explicit representation for missing bytes.

Bounded fixtures now abort formatting both before the first payload commits and
after one full sector, using motor-off, controller reset and drive-door opening.
They check every retained payload byte, the unrelated drive, write count and EDSK
validity. Existing underrun tests cover loss of the next ID tuple. Partial-ID and
partial-gap formatting remain outside the sector-image representation.
