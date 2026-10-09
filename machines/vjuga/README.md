# VJUGA

VJUGA is an existing Z80-based Juku relative, with adapted firmware and a VGA-oriented hardware design. Its current T80/tv80 models and physical evidence live in [8080-cosim/spinoffs/minimal-vga](https://github.com/ddanila/8080-cosim/tree/master/spinoffs/minimal-vga).

The extracted Juku C core supplies the bounded framebuffer oracle used by the tv80 boot check. Full HDL execution was deferred during extraction; this is an opt-in harness, not a passing qualification claim. `tests/differential/vjuga_compare.py` runs the adapted ROM on tv80 in both decode modes and compares the framebuffer at 6,000 video writes. This checks the existing compatible-subset boot workload, not arbitrary Z80 software, complete BIOS compatibility, or a full VJUGA software emulator.

A portable VJUGA core should use the same Z80 CPU dependency as Robotron while keeping board-specific wiring, firmware, memory decoding, interrupts, and video separate. Juku device code should be shared only where its behavior matches the selected VJUGA revision. No Z80 software core has been selected or imported yet.
