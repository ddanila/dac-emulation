# Juku hardware profiles

Profiles configure hardware independently of firmware bytes. The registry in
`machines/juku/profiles.inc` owns stable IDs, names, controller placement and
keyboard selection. The default remains `mainboard-juku`. Qualification evidence
is in [results.json](results.json); the default-profile compatibility matrix is
in [regression.json](regression.json). The original and checksum-corrected #0043
comparison is in [checksum-results.json](checksum-results.json).

| ID | Controller | Keyboard | Firmware association |
| --- | --- | --- | --- |
| `mainboard-juku` | Mainboard FD1793 | Juku | #0031, #0037 |
| `mainboard-juss` | Mainboard FD1793 | JUSS | #0035 |
| `early-juss` | Mainboard FD1791 | JUSS | #0024 |
| `early-juku` | Mainboard FD1791 | Juku | Monitor 3.3 |
| `card-juku` | Expansion FD1793 | Juku | #0032 |
| `card-at` | Expansion FD1793 | AT adapter | #0043 |
| `single-density` | Mainboard FD1792 | JUSS | Generated diagnostics; historical pairing unverified |

The emulator performs no ROM recognition, checksum repair, guest-memory input injection or profile
selection based on a disk's contents is performed. The native runner's explicit
`JUKU_FDC_BUS_INVERT` override remains diagnostic. Timing mode is independent of
profile selection; experimental FDC synchronization remains opt-in.

## Interfaces and lifecycle

`juku_set_profile(machine, index)` selects a profile before execution.
`dac_juku_set_profile(session, index)` selects one while powered off; the shared
runtime applies it at power-on and preserves it across reset. Invalid selections
and powered-on changes fail. `dac_juku_profile_count`, `dac_juku_profile_id`,
`dac_juku_profile_name`, `dac_juku_profile_firmware` and
`dac_juku_get_profile` expose the same registry to native and WASM clients.

The native runner accepts `--list-profiles` or `--profile ID` before its existing
positional arguments. Scenario JSON accepts `juku_profile: "ID"` for Juku.
Snapshots include profile, controller, card latch, keyboard shift-latch state and
media metadata. Profile mismatches are rejected before mutation. The snapshot
version changes; older states require their original archived core.

Museum profile selection is available while powered off. Checkpoints, recordings
and state compatibility keys include the profile; disk library identity remains
independent. Absent profile metadata means the original default. Nondefault
profiles require an API-capable core. Recording envelope/transport version 3
carries nondefault profiles; versions 1/2 retain their original default behavior.

## Hardware contract and limits

The [WD FD179X datasheet](https://bitsavers.trailing-edge.com/components/westernDigital/FD179X-01_Data_Sheet_Oct1979.pdf)
defines FD1791/1792 inverted DAL and FD1793 true DAL. FD1792 is FM-only; FD1791
and FD1793 select encoding from DDEN. Mainboard registers occupy `1C–1F`, with
PPI PC4 supplying DDEN. The sibling `8080-cosim/docs/fdc-hardware-handoff.md`
identifies the corresponding D26.13–D93.37 net.

Card firmware #0032/#0043 uses registers `30–33`, control latch `34`, and a
seek-data alias at `35`. The provisional control mapping is motor bit 2, clock
bit 3, DDEN bit 4, drive bit 5 and side bit 6. It is inferred from the ROM's
drive-selection and transfer routines; it is not a physical timing measurement.
Mainboard PPI writes do not drive the card controller. Inactive FDC ports are
not aliases of the selected controller.

The #0043 AT adapter exposes translated scan-set-1 bytes through PB7 (ready)
and PB0 (serial data), clocked by PA5 and acknowledged/reset by PA7. Its queue,
shift position, make/break codes and modifier state are modeled at the PPI
interface. This is a firmware-derived adapter contract, not a complete PC 8042
or PS/2 electrical model. The preserved ROM's block-1 checksum discrepancy prevents startup. An explicitly
corrected copy (offset `0x000A`, `F2` to `57`, calculated from bytes `0x000B..0x07FF`)
boots EKDOS and passes guest file creation, write/read/EOF and host persisted-file
verification in both timing modes. Only that checksum byte differs; the emulator
does not alter either ROM. The adapter reloads bit zero on receipt of a new byte,
including after disk firmware clocks an empty adapter. JUSS supports the
verified alphanumeric, punctuation, modifier and control contacts; unverified
special-key legends must not be inferred from the Juku keyboard layout.

## Media

Raw `.juk` files retain the 80-track, one/two-sided, ten-sector, 512-byte MFM
interpretation. IMD import follows the
[original ImageDisk format](https://github.com/andreas-jonsson/imagedisk).
The supported subset is modes 2/5 (FM/MFM at the 250 kbit/s controller-rate
setting), up to 80 cylinders, two sides, 32 sectors per track, and 128–2048-byte
sectors. Other modes, larger sectors, duplicate sector IDs/tracks and malformed
input are rejected explicitly. Imported images are bounded to 2 MiB after
normalization. This is sector-level media, not flux preservation.

IMD compression is expanded into a private copy. Sector order, ID cylinder/head
maps, missing records, deleted marks and recorded data errors are retained.
Export returns a valid uncompressed IMD, not a raw image with lost metadata.
Guest writes clear the affected sector's data-error flag. Formatting rewrites
existing sector slots; changing geometry or creating a missing slot is not
supported and reports a controller error. FM and MFM use different address marks,
CRCs, byte windows and revolution lengths. A density mismatch cannot read sector
payloads successfully.

Native IMD mounting also uses a private temporary copy. Set
`JUKU_DISK_EXPORT=/path/to/session.imd` to export it at shutdown. Existing native
raw-disk writable behavior is unchanged. IMD metadata replaces raw deleted-mark
sidecars; attaching a sidecar to IMD is rejected.

## Verification

```sh
make test-juku-profiles test-juku-fdc-variants test-juku-fdc-sync
make test-juku-profiles-sanitize
make test-juku-profiles-wasm EMCC=/path/to/emcc
python3 verification/juku-profiles/run.py \
  --roms ../8080-cosim/roms --base /path/to/prog1.juk \
  --output /tmp/juku-profile-study
```

The real-ROM matrix uses public profile/key APIs and unmodified firmware, in both
timing builds. #0035's monitor boots with `T`; the other tested Ekta setups use
`TDD`. The guest checks eight file records and EOF; host verification checks the
persisted file and unrelated bytes. Monitor 3.3 uses the exact 13-sector generated
bootstrap because a compatible historical OS disk has not been qualified.
FD1792 tests use generated FM media, including a real CPU bootstrap, formatting,
readback, density mismatch and IMD snapshot restoration. Reports distinguish
these diagnostics from historical software compatibility.

To reproduce the #0043 comparison, including a derived checksum-corrected ROM:

```sh
python3 verification/juku-profiles/run.py \
  --roms ../8080-cosim/roms --base /path/to/prog1.juk \
  --output /tmp/juku43-checksum-study --only ekta43 --include-corrected-ekta43
```

The derived ROM is written only into the output directory. The report records
both ROM hashes and the changed offset/value; the source ROM is untouched.
