# CPU dependencies

`i8080/` is Nicolas Allemand's MIT-licensed core, imported unchanged from the pinned `8080-cosim` revision. Its original `I8080_LICENSE` is retained; file hashes and source paths are in [juku-source.json](../../docs/juku-source.json).

`chips/z80.h` is Andre Weissflog’s unmodified cycle-stepped Z80, pinned at `9e88298ce56319953ac7a43213a1120359f7a3a6` under its zlib/libpng license. Both VJUGA and Robotron use the same `common/cpu/z80` bus adapter. Upstream tests and source hashes are recorded in [z80-provenance.json](../../docs/z80-provenance.json).
