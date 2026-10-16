# Robotron debugger and printer readiness

The browser debugger is a host tool, not a guest device. Pause retains power and
machine state. Step runs clocks until the next Z80 instruction boundary; if the
CPU was already mid-instruction it completes that instruction. DMA and devices
continue for those clocks. A 100,000-clock bound prevents an indefinite wait.
Mapped memory/disassembly reads do not perform bus cycles or consume device data.
Read/write mappings are reported independently through the CAS PROM decoder.
Bus-event breakpoints stop after the clock that emitted the event; they are not
pre-instruction breakpoints. Debug controls/capture buffers are not saved as guest
state. The unchanged chips disassembler has its own retained zlib notice.

## Printer

The [1715W/M schematic archive](https://xepb.org/robotron/docs/1715w.zip),
`Stromlaufplan D.jpg`, connects printer X4 readiness 106A to SIO A CTS and TXDA
to printer data 103A. The [Zilog Z80 peripherals manual](https://www.zilog.com/docs/z80/um0081.pdf)
describes CTS, WR3 Auto Enables, RR0 and external/status interrupts.

Ready asserts CTS. Busy, offline and paper-out are three host descriptions of the
same deasserted wire; the guest cannot distinguish them through CTS. With Auto
Enables, a waiting byte starts only when ready. A frame already started finishes.
Without Auto Enables, a frame starting while not ready is counted as lost by the
virtual receiver; this receiver policy is not a measured Robotron printer model.
CTS transitions can latch an external/status interrupt, with channel A priority
above channel B. WR0 resets the latch; RETI/return-from-interrupt releases service.
Capture remains limited to 64 KB. No particular printer escape language or paper
transport is claimed. State and in-flight acceptance are included in Robotron
snapshot layout 12; readiness remains attached across reset/power cycling.

Recording opcode 19 carries readiness 0..3 in DAC-recording-2 and native DACR2.
Old recordings still run with their preserved cores; cross-build state migration
is not claimed. Focused native tests cover readiness gating, loss, in-flight
completion, vector priority, reset and snapshot continuation.

## Execution targets and independent clock fixtures (0.14.0)

`dac_debug_target` arms a logical 16-bit CPU address. Debug-run stops at the
completed opcode-fetch boundary for that address (hit reason 2); it does not
undo fetch bus activity. Clearing breakpoints clears execution and event stops.
The target is host state and is deliberately excluded from snapshots.

`robotron_v24_transmit_clock` now accepts TX clock edges independently of
`robotron_v24_receive_clock` RX samples. The existing CTC wrapper still supplies
both, preserving the museum board configuration. This is a native diagnostic
interface, not a newly asserted external-clock connector or jumper route.
No external clock generator is exposed in the browser.

The Zilog manual, printed pages 232 and 285–287, specifies falling-edge TX,
1/1.5/2 stop bits, divisors 1/16/32/64 and external synchronization for x1 RX.
Focused fixtures cover independent/stalled RX and TX, received data with no TX
edges, and 8N1.5 completion for all four divisors on both transmitters. Existing
runtime fixtures verify snapshot continuation of queued serial input and phase.
For x16/x32/x64, 1.5 stop bits are integral clock counts. At x1 the aggregate TX
capture still rounds 10.5 clocks up to 11 for 8N1.5. The independently timed peer
waveform already preserves 21 half-cells. An inferred midpoint capture would not
establish exact SIO pin-edge behavior: sub-edge scheduling and a qualified clock
waveform are still needed. Synchronous SIO modes remain outside this model.

## Explicit clock pins and mixed continuation (0.15.0)

`robotron_serial_edge(machine, channel, transmit, level, input)` adds a native
fixture interface for both channels: RX samples only rising edges; TX starts a
character only on a falling edge. Repeating a level is not an edge. Alternating
TX edges represent equal half-periods of an **ideal diagnostic clock**. Remaining
frame time is stored in half-clock units, so the ideal x1 8N1.5 fixture completes
21 half-periods after its starting edge, without rounding to 11 periods. Fixtures
cover both transmitters, all four divisors and all three stop-bit choices, stalled
RX/TX independence, duplicate levels and reset. Do not mix edge and aggregate
clock APIs within a frame.

This does **not** turn CTC ZC/TO pulses into a measured square wave. The museum
board still uses the existing aggregate CTC route; its x1 half-stop capture is
still quantized to a whole callback. The Zilog manual establishes the programmed
format and edge polarity, but not a specimen-qualified x1 half-stop completion
phase under arbitrary clock duty cycles. SIO/CTC propagation, physical duty cycle,
and this machine's exact routing need separate qualification before changing that
route. The explicit fixture is a tool for that work, not a new hardware claim.
See [Zilog UM008101](https://www.zilog.com/docs/z80/um0081.pdf), printed pp.232,
285–288; in particular WR5 says an already-started character finishes after TX is
disabled. The printer now obeys that rule instead of stranding the frame.

Robotron snapshot layout **13** stores half-clock remainder and diagnostic pin
levels. Bounds reject inconsistent remaining-time fields. Cross-build migration
is not implied: the museum retains 0.14.0 by hash for old states/recordings.

The mixed runtime fixture uses a newly written test ROM concurrently exercises a 32-byte DMA
copy, a two-track seek, printer and V.24 TX, queued serial RX, keyboard character-adapter input,
and IM1 interrupt service. It saves between a DMA read and write, then compares
six subsequent boundaries using batched versus single-clock execution. Full
snapshots and bus transcript hashes agree; assertions prove that each workload
ran, rather than merely comparing two idle machines. It uses fewer than 64,000
emulated clocks per instance, blank media, no historical OS and no Verilog.

The mixed runtime fixture now runs twice: once with the character adapter and
once with an original 2 KiB keyboard test ROM. The latter scans a matrix switch
through the keyboard Z80, emits `K` through serial strobes, exercises LED latches,
and waits for release before clearing them. The main CPU concurrently executes
DMA, seek, printer/V24 and interrupt work. Six snapshot continuation boundaries
compare complete serialized state and trace hashes for batched versus one-clock
execution, followed by a release/LED state comparison. Each instance stays below
66,000 clocks. No historical ROM, OS boot or HDL is required; this does not claim
full S600 qualification or identify the specimen's replacement EPROM.
