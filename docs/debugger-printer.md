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
