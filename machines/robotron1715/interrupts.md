# Ordinary 1715 motherboard interrupt chain

`pc1715_onboard_enable` before CPU execution enables register-level CTC/SIO
peripherals. Reset retains this selection, clears peripheral state and resets the
card. Default legacy mode leaves those ports to the existing external keyboard
fixture; the W/M profile is unchanged. Native clients must rebuild because the
board struct grew. No snapshot format is introduced.

The classic-board order is X2 floppy controller, CTC channels 0–3, then SIO A
receive/transmit/external and B receive/transmit/external. A pending higher
priority source can preempt a lower in-service source. An in-service source blocks
itself and all lower sources. Acknowledge selects just one eligible source; RETI
releases just the highest-priority in-service source, not every peripheral. The
card callback is no longer given RETIs belonging to motherboard devices. An
unowned acknowledge returns FFh; an unowned RETI has no effect.

Wiring evidence: original ZRE 1.93.300101.5/04 and floppy sheet
1.93.300102.3/04, recorded in
[Pico1715's X2 contact review](https://github.com/ddanila/Pico1715/blob/main/hardware/x2-pinout.md).
Those sheets put X2 A10 at CTC IEI, CTC IEO at SIO IEI, and SIO IEO at X1 B10.
The priority/state rules and vector layouts follow the
[Zilog Z80 CPU Peripherals User Manual UM008101](https://www.zilog.com/docs/z80/um0081.pdf),
CTC interrupt control and SIO interrupt handling/register sections. The 2009
redraw's inconsistent X1/A10 label is not used to reverse the chain.

## Supported register-level subset

- 08h–0Bh: four CTC channels, control/time-constant words, channel-0 vector base,
  constant zero as 256, prescale 16/256, automatic or externally started timers,
  and edge-selected counters. `pc1715_ctc_input` supplies external levels. Timers
  count CPU T-states even while the external card stalls a normal I/O transaction.
- 0Ch/0Dh: SIO A/B data; 0Eh/0Fh: A/B control. Register pointer writes, WR1
  interrupt enables, WR2 B vector/status-affects-vector, WR3 receive enable and
  WR5 transmit enable. A three-byte completed-receive FIFO supplies ordinary
  receive interrupts; first-character mode and enable-next-character are tracked.
  Transmit writes complete at the next peripheral tick, allowing TX-empty
  interrupts. `pc1715_sio_external` supplies an already-qualified external/status
  transition. WR0 clears TX/external/error requests, resets a channel, or returns
  from the highest SIO service. RR0 exposes FIFO availability/TX-empty, RR1 errors
  and all-sent, and RR2 the base vector.
- Ordinary modified SIO vectors are A RX/TX/EXT: base|0C/08/0A, B: base|04/00/02,
  replacing bits 1–3. CTC vectors replace bits 1–2 with channel number.

`pc1715_irq_pending`, `pc1715_irq_ack`, `pc1715_irq_reti` expose deterministic
native test seams used by the same CPU callbacks. Direct onboard read/write
seams do not generate CPU trace events; actual IN/OUT do. In enabled mode the
onboard ports bypass external read/write/wait callbacks, so a card cannot stall
or double-drive an onboard peripheral transaction.

`pc1715_card_quiesce` models an isolated X2 card: it stops its callbacks and
releases its priority-chain ownership until board reset. It does not flush card
storage, reset the CPU or erase pending motherboard interrupts. Like hardware
removal, releasing a card while its ISR is running does not cancel that CPU
routine. A later RETI propagates to whatever downstream service remains; software
must coordinate shutdown rather than assume removal unwinds nested ISR stacks.

## Qualification and explicit limits

`make test-pc1715` and `make test-runtime-sanitize` exercise simultaneous sources,
card/CTC/SIO nesting, all six ordinary SIO vector classes, no stray card RETI,
card isolation, reset, timer/counter programming, constant zero, falling edges,
timer progress during WAIT and a synthetic IM2 program using real OUT/RETI cycles.
Pico1715 additionally runs the chain with its real controller model.

This closes the **card–CTC–SIO interrupt arbitration** gap, not full motherboard
peripheral emulation. X1 downstream expansion devices are not attached/modelled.
CTC output clocks are not wired to SIO serial waveforms; input levels/completed
bytes are explicit native seams. No baud/framing, synchronous modes, modem-line
latching, silicon FIFO-overrun replacement, special-receive vectors, DMA/WAIT
handshake, complete RR0/RR1/RR2 status or display implementation is claimed.
Receive injection returns ENOSPC at FIFO capacity (and latches RR1 overrun); this
is fixture backpressure, not exact silicon overrun behavior. Serial TX completion
in one T-state is a scheduling seam, not baud-rate timing. Do not use these tests
to certify electrical priority timing or keyboard/serial compatibility.
