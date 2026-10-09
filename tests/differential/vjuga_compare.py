#!/usr/bin/env python3
"""Preserve the existing bounded VJUGA tv80 boot/framebuffer comparison.

This is not a full software Z80 emulator qualification. VJUGA executes its
adapted ROM on tv80; the extracted 8080 Juku core supplies the existing
compatible-subset framebuffer oracle at 6,000 video writes.
"""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    args = p.parse_args()
    source = args.source.resolve()
    vjuga = source / "spinoffs/minimal-vga"
    tv = vjuga / "external/tv80/rtl/core"
    if not (tv / "tv80s.v").is_file():
        raise SystemExit("Initialize the reference checkout's tv80 submodule before this check")
    env = {k: v for k, v in os.environ.items() if not k.startswith("JUKU_")}
    with tempfile.TemporaryDirectory(prefix="dac-vjuga-") as tmp:
        work = Path(tmp)
        def run(command):
            result = subprocess.run([str(x) for x in command], cwd=work, env=env,
                                    capture_output=True, text=True, timeout=300)
            if result.returncode:
                raise AssertionError(result.stdout[-2000:] + result.stderr[-2000:])
            return result
        rom = vjuga / "roms/ekta37_z80.bin"
        hexfile = work / "rom.hex"
        hexfile.write_text("".join(f"{b:02x}\n" for b in rom.read_bytes()))
        run([ROOT / "build/juku-trace", rom, "50000000", "6000"])
        expected = (work / "vram.bin").read_bytes()
        run([ROOT / "build/juku-trace", source / "roms/ekta37.bin", "50000000", "6000"])
        assert (work / "vram.bin").read_bytes() == expected, "adapted ROM changed bounded 8080 framebuffer"
        for mode in (0, 1):
            output = work / f"vjuga-{mode}.bin"
            executable = work / f"vjuga-{mode}.vvp"
            run(["iverilog", "-g2012", f'-Pvjuga_juku_tb.rom_file="{hexfile}"',
                 "-Pvjuga_juku_tb.vw_limit=6000", f"-Pvjuga_juku_tb.decode_mode={mode}",
                 f'-Pvjuga_juku_tb.dump_file="{output}"', "-o", executable,
                 source / "hdl/vendor/vm80a.v",
                 *[tv / name for name in ("tv80_alu.v", "tv80_reg.v", "tv80_mcode.v", "tv80_core.v", "tv80s.v")],
                 source / "hdl/devices.v", vjuga / "hdl/u24_dram_timing.v",
                 vjuga / "hdl/vjuga_juku_top.v", vjuga / "hdl/vjuga_juku_tb.v"])
            run(["vvp", executable])
            assert output.read_bytes() == expected, f"VJUGA decode mode {mode} differs"
            print(f"PASS: VJUGA tv80 decode mode {mode} matches extracted Juku oracle at 6000 video writes", flush=True)


if __name__ == "__main__": main()
