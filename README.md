# DAC Emulation

Portable emulation cores for [Danila’s Archive of Computing](https://github.com/ddanila/dac).

The goal is to run the same machine implementation in native verification tools and in browser museum exhibits. The first extracted core is the Juku E5104 from [8080-cosim](https://github.com/ddanila/8080-cosim). VJUGA and Robotron 1715M share a Z80 CPU dependency with separate machine implementations.

## Status

Juku now builds as an instance-based C library and a native compatibility runner. Shared tracing and callback-backed media are implemented. `8080-cosim` now pins this core and preserves its legacy build paths through forwarding files. VJUGA now has a bounded-boot Z80 profile; the experimental Robotron profile boots TOS/M with keyboard, two-drive disk operations, serial-printer capture and same-build snapshots. All three cores build for WebAssembly and connect to the DAC prototype. See [validation and limitations](docs/z80-browser-validation.md).

```sh
make -j4
make test
```

`make test` is the fast intermediate check: no Verilog, firmware downloads, PTYs, or full-system boot. Extended comparisons are explicitly opt-in. See [extraction and validation](docs/juku-extraction.md) for results and outstanding upstream failures.

## Shared verification

Juku and Robotron 1715M share the session runtime and a bounded, data-driven
scenario runner with memory assertions, reproducible evidence and trace
comparison. Native replay and the browser use the same runtime; existing build
paths remain compatible. See [verification and target boundaries](docs/verification.md).
The original-ROM-free example scenarios are included in `make test`.

## Layout

| Path | Responsibility |
| --- | --- |
| `common/runtime/` | Shared native/browser session and read-only observation API |
| `verification/` | Bounded scenarios, provenance reports and first-divergence comparison |
| `common/trace/` | Shared trace events and diagnostic output interfaces |
| `common/media/` | Disk-image storage and sector metadata, independent of controllers |
| `machines/juku/` | Juku machine core and machine-specific devices |
| `machines/vjuga/` | Functional Z80 bounded-boot profile and HDL reference |
| `machines/robotron1715m/` | Experimental Robotron banked Z80 machine and devices |
| `third_party/cpu/` | Pinned CPU dependencies with their original notices |
| `runners/native/` | Native CLI, files, terminal transport, and host pacing |
| `runners/browser/` | WebAssembly integration, browser input, scheduling, and output |
| `tests/differential/` | Comparisons with independent implementations |
| `tests/integration/` | Complete boot and interaction scenarios |

## Repository boundaries

- **dac:** museum UI, exhibits, 3D interactions, and asset references.
- **dac-emulation:** portable cores, shared utilities, runners, and behavioral tests.
- **8080-cosim:** Juku hardware reconstruction, HDL, physical evidence, and co-simulation harnesses. It pins this core and retains legacy compilation paths for existing consumers.
- **juku-common:** shared guest software that runs on Juku, including assembly diagnostics, console, and boot/transport routines.
- **cpmish / cpm-plus-juku:** their operating-system implementations and integration tests.

See the [architecture and interface proposal](docs/architecture.md) and [migration sequence](docs/migration.md). The architecture distinguishes implemented foundations from the proposed museum interface.

## License

Original project code and documentation are licensed under the [MIT License](LICENSE).

Imported dependencies and adapted code retain their original licenses and notices. Do not relabel third-party code as MIT. Firmware, disk images, and other historical media are separate from the emulator code; none are included here.

Browser API 0.8.1 adds `dac_drive_transfer(session, from, to)`. Both levers
must be open, the source disk removed, and the destination physically empty.
A retained ejected destination image moves into the vacated parking slot.
The operation swaps existing byte buffers, parsed track layouts and protection
atomically, without moving the physical drive's head or spindle state. Active
FDC commands reject transfer. Recording opcode 11 applies the same operation in
browser and native replay. The snapshot memory layout is unchanged.

Browser 0.8.2 adds `dac_drive_protect(session, unit, protected)`: a removed
Robotron disk can have its notch covered/uncovered without remounting, resetting
mechanics, or replacing bytes. Inserted/absent disks reject the operation.
Native/browser recording opcode 12 preserves these transitions. TEAC FD-55
maintenance documentation describes a covered notch as write protected.

### 0.9.0: V.24 and explicit connection experiments

Robotron SIO channel B now provides a bounded asynchronous virtual peer. The
reference internal clock is CTC0 ZC/TO1 through the S1 selection path in
`1715W/teil_b/Stromlaufplan D.jpg` ([W/M archive](https://xepb.org/robotron/docs/1715w.zip)).
Guest code must initialize WR3/WR4/WR5 and CTC channel 1. Framing follows guest
word width/parity/divisor; the adaptive receiver sends two stop bits for the
1.5-stop setting. No external-clock, synchronous-mode or external/status interrupt
latching implementation is claimed. Register behavior follows the
[Zilog peripherals manual](https://www.zilog.com/docs/z80/um0081.pdf).

Runtime APIs: `dac_serial_send` queues one byte (powered Robotron only),
`dac_serial_signals` sets CTS=1, DCD=2, optional peer-honors-RTS=4. Status returns
these bits plus pending input count shifted by 8. Input and output each hold up
to 65536 bytes; output overflow latches until `dac_serial_clear`. Data/size expose
raw capture. The guest sees a separate three-byte RX FIFO, overrun, receive and
transmit interrupts, and CTS auto-enable gating. CTS prevents a new TX frame,
not completion of one already in flight. DCD indicates a connected peer.
Reset clears serial buffers but retains connection flags.

`dac_cables(mask)` explicitly disconnects keyboard power/data (1) and monitor
video (2). Keyboard CPU execution/input stops; reconnecting cold-starts the
keyboard with the same ROM. Monitor disconnection blanks output without stopping
the guest or modifying video RAM. These are opt-in functional experiments, not
an analogue power model. Reset/power retain the mask. Snapshot layout **9** stores
serial queues/phase and connection state. DACR2 replay adds serial/connection
events and serial capture; DACR1 remains accepted.

Focused checks cover FIFO/overrun, CTS/RTS, CTC clocking, vectors/RETI, exact
snapshot continuation, and S600 REP/modifier transitions. An optional independent
MAME comparison runs an original bounded diagnostic, with the supplied CAS and
S600 ROMs, in both implementations:

```sh
python3 tools/compare_robotron_mame.py --media ../dac/public/media/robotron \
  --mame /path/to/mame --output /tmp/robotron-comparison.json
```

MAME is not required by normal CI. The original diagnostic intentionally differs
from S550, so MAME's ROM checksum warning is expected. The comparison covers
memory, DMA, ordered I/O, an IM2 CTC interrupt and display character RAM. It does
not certify raster timing or physical hardware. No MAME implementation is copied
into this harness. The museum keeps the previous core for older snapshots.
