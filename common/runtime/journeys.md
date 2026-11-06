# Journey observation ABI 1

`dac_journey_capabilities(session)` returns 1 for Robotron W/M. `dac_journey_words()` returns 96. The API is additive; ordinary saved machine state and the 54-word keyboard ABI retain their layouts. Host observation buffers are excluded from saves.

`capture(mask)` starts a bounded capture (131072 records), `stop()` stops it, `count()` and `data(first)` expose records, and `status()` reports 1 capturing, 2 stopped, 3 full. Mask bit 0 retains instruction/keyboard detail, bit 1 all bus events, bit 2 glyph scanlines for `select(cell)` (0–1919). Mask zero produces an aggregated overview. `arm(kind,address,mask,stop)` starts capture and sets debug hit 3 on the first matching event; address 65536 is wildcard. `trigger()` is its one-based index. This ABI has no pre-trigger ring.

All words are uint32. Clock is low/high words 0/1 in the existing 3.9936 MHz machine clock. Words 0–53 preserve [keyboard record fields](keyboard-dive.md). Additional events: 12 MR, 13 MW, 14 IR, 15 IW, 16 interrupt acknowledge bus; 20 accepted source+1/vector; 21 RETI; 22 glyph scanline; 24 peripheral transition; 25 capture start; 26 first mapped page execution; 30 interrupt arbitration; 40 explicit fault; 41 suppressed strobe. Existing kinds 1–11 retain their meanings.

| Words | Meaning |
| --- | --- |
| 54–56 | Bus master, mapped space, backing offset |
| 57 | FDC phase (bits 0–3), search (4+), command byte (8+), write (16), pending (24) |
| 58 | Unit, cylinder, head, sector in successive bytes |
| 59 | FDC byte position low16 / length high16 |
| 60 | First four FDC command bytes |
| 61 | ST0, ST1, ST2, result position in successive bytes |
| 62–63 | DMA remaining; run A low16 / B high16 |
| 64 | DRQ, DMA ready, bus-owned, eligible IRQ, terminal count (bits 0–4) |
| 65 | Pending source mask low16, in-service high16 |
| 66–69 | Raster row/character; frame; cursor column/row; four CRTC config bytes |
| 70–77 | Two drive phases, two head positions, two mechanics bitfields, two STEP counts |
| 78–81 | Mainboard PC mapped space high8/offset low24; raster stream; CPU pins low/high |
| 82–87 | DMA transferred; DMA status/control; CTC vector; SIO vector; CTC counter/constant; CTC control |
| 88–91 | Display on/underrun/stopped bits; word at SP; FDC command position/result length; motor |
| 92–95 | Experiment kind; strobe counter; eligible source+1 (0 none); aggregate count |

Source IDs are DMA 1, CTC channels 2–5, SIO A receive 6, A transmit 7, B receive 8, B transmit 9, B external 10, A external 11. Priority matches `interrupt_source`, including in-service blocking; numeric IDs alone do not specify external-interrupt priority.

Glyph event address packs cell low16 and line bits16–23. Value packs emitted byte low8, raw byte next8, glyph offset high16. Dot expansion is derived from these actual sampled scanline bytes, not a dot-clock capture.

Overview skips CPU reads and non-video writes, samples DMA at transfer boundaries/256-byte intervals, aggregates identical status polls and bank-register writes at matching PC/bank, and coalesces consecutive equal video writes. It preserves first mapped-page visits rather than instructions. An aggregate row's clock and registers belong to its first observation. Omitted pulse timing cannot be inferred.

`peek(space,address)` reads RAM(1), ROM(2), VRAM(3), glyph(4), PROM(7) without advancing state. `fault(kind,address,value)` is for isolated experimental sessions: held matrix contact(1), suppress ordinal keyboard strobe(2), XOR keyboard ROM(3), eject drive A(4), sector CRC(5; RRHHCC), inhibit CPU interrupt acceptance for value clocks(6), XOR glyph(7), protect disk A(8). Kind zero clears the overlay and releases a held contact; it does not undo prior ROM/media/glyph mutations. Discard the branch or restore an appropriate original checkpoint. Host wrappers must retain fault actions for replay; ordinary machine saves are not a portable fault schedule.

Native test: `make test-journey`. WASM parity: `make test-journey-wasm NODE=/path/to/node EMCC=/path/to/emcc`. The test fixture compares every record and verifies observation state neutrality, replay, mutation isolation and trigger behavior. Browser scenario programs and deterministic replay orchestration live in `ddanila/dac`.
