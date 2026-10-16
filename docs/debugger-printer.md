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
