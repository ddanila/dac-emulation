# VJUGA

VJUGA is an existing Z80 Juku relative with adapted firmware. Its hardware models and physical evidence remain in [8080-cosim/spinoffs/minimal-vga](https://github.com/ddanila/8080-cosim/tree/master/spinoffs/minimal-vga).

`vjuga.c` implements the functional Rev-A bounded-boot profile: shared software Z80, 64 KB RAM, 16 KB ROM, Mode B overlay decoding or Mode A fixed low-ROM selection, port latches, and Port C/BSR decoding. At 6,000 video writes, both modes match the established Juku compatible-subset framebuffer oracle. Run the fast comparison with:

```sh
make
python3 tests/differential/vjuga_native.py ../8080-cosim
```

This profile does not model DRAM wait states, refresh timing, IRQ, keyboard, floppy or all later board revisions. It is a bounded boot implementation, not a complete VJUGA system. The browser offers its Mode B profile and labels the absent interactive devices.

The optional `tests/differential/vjuga_compare.py` is the slower tv80 HDL comparison and has not been rerun. VJUGA and Robotron share only the CPU dependency/adapter, not board-specific wiring.
