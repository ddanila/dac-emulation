#!/usr/bin/env python3
"""Run existing Juku regressions against DAC's extracted implementation.

The reference checkout is read-only: all compilation and generated outputs
live in a temporary directory. Historical ROM/media stay in that checkout.
"""
import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--hdl", action="store_true")
    parser.add_argument("--serial", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    candidate = ROOT / "build/juku-trace"
    env = {k: v for k, v in os.environ.items() if not k.startswith("JUKU_")}
    with tempfile.TemporaryDirectory(prefix="dac-upstream-") as tmp:
        work = Path(tmp)
        # A few inherited C fixtures use repository-relative read-only inputs.
        (work / "roms").symlink_to(source / "roms", target_is_directory=True)
        (work / "media").symlink_to(source / "media", target_is_directory=True)

        def run(command, **kwargs):
            return subprocess.run([str(x) for x in command], cwd=work, env=env,
                                  check=True, timeout=300, **kwargs)

        def compile_test(name, native_disk=False):
            command = [os.environ.get("CC", "cc"), "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror"]
            for include in ("machines/juku", "third_party/cpu/i8080", "common/media", "common/trace"):
                command += ["-I", ROOT / include]
            # Upstream tests use ../cosim headers. Redirect only includes so
            # their struct layouts come from the extracted implementation.
            test_source = work / (name + ".c")
            test_source.write_text((source / "tests" / (name + ".c")).read_text()
                                   .replace('"../cosim/', '"'))
            command += [test_source]
            if native_disk: command += [ROOT / "runners/native/juku_disk_file.c"]
            command += [ROOT / "build/libdac-juku.a", "-o", work / name]
            run(command)
            return work / name

        for test in ("i8080_conformance_test", "juk_disk_test", "juku_fdc_test"):
            run([compile_test(test, native_disk=True)])
        for test in ("cosim_pit_latch_test", "cosim_watch_checkpoint_test", "cosim_realtime_test"):
            run([sys.executable, source / "tests" / (test + ".py"), candidate])
        # Original ROM disk-controller init followed by its deblocking/write test.
        romwrite = compile_test("rombios_fdc_write_test", native_disk=True)
        disk_env = dict(env, JUKU_DISK=str(source / "media/disks/JUKU1.CPM"),
                        JUKU_KEYS="TDD|", JUKU_KEY_HOLD_FRAMES="6", JUKU_KEY_GAP_FRAMES="8",
                        JUKU_CHECKPOINT_PREFIX=str(work / "rombios-init"), JUKU_STOP_KEYS_DONE="1")
        subprocess.run([str(candidate), str(source / "roms/ekta37.bin"), "25000000", "0", "200000"],
                       cwd=work, env=disk_env, check=True, timeout=60,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        run([romwrite, work / "rombios-init.ram"])
        if args.serial:
            for test in ("cosim_usart_pty_test", "cosim_usart_overrun_test", "cosim_console_test"):
                run([sys.executable, source / "tests" / (test + ".py"), candidate])
        else:
            print("SKIP: serial/console PTY tests (enable with --serial)", flush=True)

        if not args.hdl:
            print("SKIP: HDL differentials (enable with --hdl)", flush=True)
            return
        if not shutil.which("iverilog") or not shutil.which("vvp"):
            raise SystemExit("--hdl requires iverilog and vvp")
        cpu = compile_test("i8080_vector_runner")
        cpu_hdl = work / "cpu.vvp"
        run(["iverilog", "-g2012", "-s", "i8080_vm80a_diff_tb", "-o", cpu_hdl,
             source / "hdl/vendor/vm80a.v", source / "hdl/sim/i8080_vm80a_diff_tb.v"])
        run([sys.executable, source / "tests/i8080_vm80a_diff_test.py", cpu, cpu_hdl])
        fdc = compile_test("fdc_vector_runner", native_disk=True)
        fdc_hdl = work / "fdc.vvp"
        run(["iverilog", "-g2012", "-DFDC_BYTE_TIMING", "-DFDC_TYPE_I_TIMING", "-DFDC_TYPE_II_III_TIMING",
             "-s", "fdc_cross_model_tb", "-o", fdc_hdl, source / "hdl/devices.v",
             source / "hdl/sim/fdc_cross_model_tb.v"])
        run([sys.executable, source / "tests/fdc_cross_model_test.py", fdc, fdc_hdl])

        # Testbenches read the factory ROM from this relative path.
        (work / "hdl/sim").mkdir(parents=True)
        rom = (source / "roms/ekta37.bin").read_bytes()
        (work / "hdl/sim/ekta37.hex").write_text("".join(f"{b:02x}\n" for b in rom))
        bus_hdl = work / "bus.vvp"
        run(["iverilog", "-g2012", "-o", bus_hdl, source / "hdl/vendor/vm80a.v",
             source / "hdl/devices.v", source / "hdl/juku_top.v",
             source / "hdl/sim/cosim_ctrace_tb.v"])
        for name, limit, frames in (("boot", 130000, 0), ("inta", 500, 1000)):
            image = source / "roms/ekta37.bin"
            extra = []
            if name == "inta":
                image = work / "inta.bin"
                run([sys.executable, source / "tests/build_inta_bus_rom.py", image])
                run([sys.executable, source / "tests/build_inta_bus_rom.py", "--hex", work / "inta.hex"])
                extra = [f"+rom={work / 'inta.hex'}"]
            events = work / (name + ".events")
            trace_env = dict(env, JUKU_BUS_TRACE=str(events), JUKU_BUS_TRACE_LIMIT=str(limit))
            subprocess.run([str(candidate), str(image), "200000000" if name == "boot" else "20000", "0", str(frames)],
                           cwd=work, env=trace_env, check=True, timeout=60,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            lines = events.read_text().splitlines()
            assert len(lines) == limit, (name, len(lines), limit)
            if name == "inta":
                ia = [line.split()[2] for line in lines if line.startswith("IA ")]
                assert ia == ["cd", "d4", "fe"], ia
                first = next(i + 1 for i, line in enumerate(lines) if line.startswith("IA "))
                extra += [f"+irq_after={first - 2}"]
            output = run(["vvp", bus_hdl, f"+trace={events}", "+timecap=30000000", *extra],
                         capture_output=True, text=True)
            if "BTRACE-END" not in output.stdout:
                raise AssertionError(output.stdout + output.stderr)
            print(f"PASS: {name} C/HDL bus comparison ({limit} events)", flush=True)


if __name__ == "__main__": main()
