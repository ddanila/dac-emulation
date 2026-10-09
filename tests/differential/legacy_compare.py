#!/usr/bin/env python3
"""Compare the extracted native runner with an independently built old runner.

Uses a separate source checkout for ROMs/media; no historical media is copied
into this repository. Both processes run in the same disposable directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    p = argparse.ArgumentParser()
    p.add_argument("source", type=Path)
    p.add_argument("baseline", type=Path)
    p.add_argument("candidate", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    source = args.source.resolve()
    cases = [
        ("stock-boot", "ekta37.bin", 5000000, 0, {}),
        ("stock-keyboard", "ekta37.bin", 12000000, 40000,
         {"JUKU_KEYS": "A", "JUKU_KEY_START_VRAM": "42000"}),
        ("disk-boot", "ekta37.bin", 25000000, 40000,
         {"JUKU_KEYS": "TDD|", "JUKU_DISK": str(source / "media/disks/JUKU1.CPM")}),
        ("ram-fault", "ekta37.bin", 500000, 0,
         {"JUKU_RAM_FAULT": "0xC123:1:0", "JUKU_WATCH_ADDRESS": "0xC123"}),
        ("cpu-fault", "ekta37.bin", 500000, 0,
         {"JUKU_CPU_A12_INCREMENT_FAULT": "1"}),
    ]
    # Every available official monitor has its own bounded reset comparison.
    for rom in sorted((source / "roms").glob("ekta*.bin")):
        if rom.name != "ekta37.bin":
            cases.append((rom.stem, rom.name, 2000000, 0, {}))
    report = {"source_commit": subprocess.check_output(
        ["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip(), "cases": []}
    for name, rom, cycles, frame, settings in cases:
        with tempfile.TemporaryDirectory(prefix="dac-juku-compare-") as tmp:
            work = Path(tmp)
            env = {k: v for k, v in os.environ.items() if not k.startswith("JUKU_")}
            env.update(settings)
            env.update(JUKU_CHECKPOINT_PREFIX=str(work / "checkpoint"),
                       JUKU_BUS_TRACE=str(work / "bus.txt"), JUKU_BUS_TRACE_LIMIT="130000",
                       JUKU_RDTRACE=str(work / "reads.txt"), JUKU_RDTRACE_LIMIT="10000",
                       JUKU_TRACE_BANK="0", JUKU_PC_HISTORY="1")
            runs = []
            for binary in (args.baseline, args.candidate):
                run = subprocess.run([str(binary.resolve()), str(source / "roms" / rom),
                                      str(cycles), "0", str(frame)], cwd=work, env=env,
                                     capture_output=True, timeout=60)
                if run.returncode:
                    raise AssertionError((name, str(binary), run.returncode, run.stderr[-1500:]))
                artifacts = {f.name: f.read_bytes() for f in work.iterdir() if f.is_file()}
                artifacts["stdout"] = run.stdout
                artifacts["stderr"] = run.stderr
                runs.append(artifacts)
                for f in work.iterdir():
                    if f.is_file(): f.unlink()
            if runs[0] != runs[1]:
                differences = [key for key in runs[0].keys() | runs[1].keys()
                               if runs[0].get(key) != runs[1].get(key)]
                if args.report:
                    failure = args.report.parent / (name + "-failure")
                    failure.mkdir(parents=True, exist_ok=True)
                    for key in differences:
                        (failure / ("baseline-" + key)).write_bytes(runs[0].get(key, b""))
                        (failure / ("candidate-" + key)).write_bytes(runs[1].get(key, b""))
                raise AssertionError((name, differences))
            report["cases"].append({"name": name, "cycles_limit": cycles,
                "rom_sha256": hashlib.sha256((source / "roms" / rom).read_bytes()).hexdigest(),
                "artifacts": {k: hashlib.sha256(v).hexdigest() for k, v in runs[0].items()
                              if k not in {"stderr", "stdout"}}})
            print("PASS", name, "(RAM, state, framebuffer, bus/read traces, stdout, stderr)", flush=True)
    if args.report: args.report.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__": main()
