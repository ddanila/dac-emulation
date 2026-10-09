# Native runner

Build with `make`, then use `build/juku-trace` in place of the original `cosim/trace` executable. It preserves the positional arguments, `JUKU_*` settings, diagnostic files, native disk adapter, PTY transport, and pacing of the pinned original implementation.

For example, run in a disposable output directory with absolute paths:

```sh
/path/to/dac-emulation/build/juku-trace /path/to/8080-cosim/roms/ekta37.bin 5000000 0 0
```

The positional values are cycle limit, video-write limit, and frame-cycle period. Firmware and disks remain external inputs. See the source runner for the complete inherited environment interface, and [validation limitations](../../docs/juku-extraction.md) before relying on automatic PTY transport.
