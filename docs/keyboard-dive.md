# Keyboard observation ABI 1

The optional keyboard dive observer records the running reference controller and
mainboard on one scheduler timeline. It never substitutes input bytes, patches
ROM or changes the CPU scheduler. `dac_dive_capabilities` returns 1 only for a
powered Robotron with keyboard firmware. Existing mainboard debug APIs are
unchanged; `dac_keyboard_reg`, `dac_keyboard_byte`, `dac_keyboard_disassemble`
and `dac_keyboard_step` provide keyboard-targeted inspection. Stepping waits for
a new instruction boundary while advancing the entire machine.

`dac_dive_capture(s,1)` starts a fresh bounded capture. `dac_dive_capture(s,0)`
stops without deleting it. `dac_dive_status` returns 1 recording, 2 stopped,
3 full, or 4 waiting for trigger (0 for null). `dac_dive_count` returns record
count; `dac_dive_data(s,first)` returns borrowed storage or NULL out of range.
Copy before advancing, rearming or destroying. Maximum: 131072 records.
`dac_dive_detail(s,0)` suppresses standalone instruction-boundary records while
retaining CPU snapshots at hardware events; the caller must identify this filter.

`dac_dive_arm(s,kind,address,pre,stop)` accepts kinds 1–11, address 0–65536
(65536 means any), prehistory 0–128, stop 0/1. `dac_dive_trigger` returns the
one-based matching record index or zero. Run with `dac_debug_run` to stop on a
trigger; `dac_debug_hit` is 3 for this condition. Stopping occurs after the
containing machine tick. `dac_dive_screen(s,cell)` reads the row-buffered character
code for cell 0–1919; it does not sample a new video frame.

Each record contains 54 uint32 words, with this layout:

| Words | Meaning |
| --- | --- |
| 0–1 | Machine scheduler clocks, low/high |
| 2 | Event kind |
| 3–4 | Event address and value |
| 5 | Keyboard clocks, low |
| 6–7 | Most recently observed keyboard/mainboard instruction addresses |
| 8–9 | Keyboard external pins, low/high |
| 10 | Receiver phase, bits, FIFO count, errors (one byte each) |
| 11–13 | Receiver shift byte, mainboard bank, write-strobe count |
| 14–30 | Keyboard PC SP AF BC DE HL IX IY AF′ BC′ DE′ HL′ IM IFF1 IFF2 I R |
| 31–47 | Same mainboard register sequence |
| 48–49 | Four instruction bytes at each retained instruction address, little-byte packed |
| 50 | SIO A WR3 and WR4 in low/high byte |
| 51–53 | Raw keyboard LED latch, keyboard clocks high, HALT bits (keyboard/mainboard) |

Event kinds: 1 contact (`column*8+bit`, down); 2 keyboard boundary (logical
address, opcode); 3 matrix input assertion (port, sensed byte); 4 serial write
strobe (bus address, normalized D0); 5 receiver advance (previous phase<<8 | bit,
level); 6 completed receiver byte (frame errors, byte); 7 SIO A data read (port,
byte); 8 mainboard boundary (address, opcode); 9 video-memory write (physical
video offset, byte); 10 changed scanout cell (row*80+column, character code);
11 external WR transition (pin mask low/high). Boundary snapshots are before the
selected instruction executes. Other event snapshots can be in-flight.
Initial instruction addresses are the current PCs until a boundary is observed.
Initial display cells establish a baseline and are not emitted as changes.

Events are ordered, including events sharing a scheduler tick. The record is not
a pin-level analog timing claim: two keyboard half edges can share a machine
timestamp. Matrix records observe the input-cycle assertion; they do not claim
continuous analog sensing. Mainboard bytes are read from current mapped memory
at the retained instruction address. `dac_dive_instruction` disassembles the
retained four-byte window; longer prefix sequences are explicitly identified.

Observer callbacks and capture allocation belong to the host, not serialized
machine state. Save clears pointers; restore rebinds trusted callbacks and clears
capture. Power cycling clears capture. The machine layout changed; archived
WASM builds own their previous save-state formats.

Run `make test-keyboard-dive` and `make test-keyboard-dive-wasm`. The first checks
complete state equivalence with observation on/off; the second compares all
native/WASM event words. Optional S600 check:
`build/keyboard-dive-test /path/to/s600.bin`.

`dac_dive_matrix(s,column,initial)` returns the effective matrix column, or the
baseline at the retained capture's beginning when `initial` is nonzero. Trigger
prehistory updates that baseline as contact records leave the window. Physical
matrix API transitions are recorded synchronously; queued tap and release-all
transitions are observed at the next keyboard clock, before the next recorded
instruction boundary. Neither path changes the contact scheduler.
