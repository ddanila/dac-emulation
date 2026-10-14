"""Versioned, bounded verification scenarios. Run: python -m verification.scenario."""

import argparse
import hashlib
import json
import time
from pathlib import Path

from .runtime import PROFILES, Runtime

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def integer(value, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f"expected integer in {low}..{high}, got {value!r}")
    return value


def fields(obj, required, optional=()):
    if (
        not isinstance(obj, dict)
        or not set(required) <= obj.keys()
        or obj.keys() - set(required) - set(optional)
    ):
        raise ValueError(f"expected fields {required}, optional {optional}")


def image(spec, base):
    if "path" in spec:
        fields(spec, ("path",))
        path = base / spec["path"]
        if path.stat().st_size > 1638400:
            raise ValueError("input exceeds supported image bound")
        return path.read_bytes()
    fields(spec, ("hex", "size"))
    data = bytes.fromhex(spec["hex"])
    size = integer(spec["size"], 1, 16384)
    if len(data) > size:
        raise ValueError("inline firmware exceeds its declared size")
    return data.ljust(size, b"\0")


def execute(document, base, library, report, events, wall_timeout=30):
    fields(
        document, ("schema", "machine", "firmware", "steps"), ("disks", "trace_limit")
    )
    if document["schema"] != "dac-scenario-1" or document["machine"] not in PROFILES:
        raise ValueError("unsupported scenario schema or machine")
    if (
        not isinstance(document["firmware"], dict)
        or not 1 <= len(document["firmware"]) <= 4
    ):
        raise ValueError("firmware must map slots to images")
    if (
        not isinstance(document["steps"], list)
        or not 1 <= len(document["steps"]) <= 10000
    ):
        raise ValueError("scenario requires 1..10000 steps")
    trace_limit = integer(document.get("trace_limit", 0), 0, 1000000)
    deadline = time.monotonic() + wall_timeout
    report.update(
        machine=document["machine"],
        profile=PROFILES[document["machine"]],
        inputs={},
        steps=[],
        trace_enabled=bool(trace_limit),
        trace_complete=True,
    )
    with Runtime(library, document["machine"], trace_limit) as runtime:
        report["runtime_build_id"] = runtime.build_id
        try:
            for slot, spec in document["firmware"].items():
                if slot not in ("0", "1", "2", "3"):
                    raise ValueError("invalid firmware slot")
                data = image(spec, base)
                runtime.load(int(slot), data)
                report["inputs"][f"firmware:{slot}"] = {
                    "size": len(data),
                    "sha256": sha(data),
                }
            disks = document.get("disks", [])
            if not isinstance(disks, list) or len(disks) > 2:
                raise ValueError("at most two disks")
            units = set()
            for disk in disks:
                fields(disk, ("unit", "path"), ("writable",))
                unit = integer(disk["unit"], 0, 1)
                if unit in units or type(disk.get("writable", False)) is not bool:
                    raise ValueError("duplicate disk unit or invalid write policy")
                units.add(unit)
                data = image({"path": disk["path"]}, base)
                runtime.mount(unit, data, disk.get("writable", False))
                report["inputs"][f"disk:{unit}"] = {
                    "size": len(data),
                    "sha256": sha(data),
                    "writable": disk.get("writable", False),
                }
            runtime.power()
            for index, step in enumerate(document["steps"]):
                if not isinstance(step, dict) or len(step) != 1:
                    raise ValueError("each step must have exactly one operation")
                op, arg = next(iter(step.items()))
                evidence = {"index": index, "operation": op, "advanced": 0}
                report["steps"].append(evidence)
                if op in ("run", "until"):
                    if op == "run":
                        limit, match = integer(arg, 1, 1000000000), None
                    else:
                        fields(arg, ("space", "address", "hex", "limit"))
                        limit = integer(arg["limit"], 1, 1000000000)
                        match = bytes.fromhex(arg["hex"])
                        if not match:
                            raise ValueError("empty until predicate")
                    while True:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("wall-clock limit exceeded")
                        if (
                            match is not None
                            and runtime.peek(arg["space"], arg["address"], len(match))
                            == match
                        ):
                            evidence["stop"] = "condition"
                            break
                        if evidence["advanced"] >= limit:
                            evidence["stop"] = "budget"
                            if match is not None:
                                raise TimeoutError(
                                    "condition not reached within emulated budget"
                                )
                            break
                        # Predicates observed at every machine step. Juku may overshoot
                        # the budget by one instruction; Robotron advances one clock.
                        quantum = (
                            1
                            if match is not None
                            else min(1000, limit - evidence["advanced"])
                        )
                        evidence["advanced"] += runtime.run(quantum)
                elif op == "expect":
                    fields(arg, ("space", "address", "hex"))
                    expected = bytes.fromhex(arg["hex"])
                    if not expected:
                        raise ValueError("empty memory assertion")
                    actual = runtime.peek(arg["space"], arg["address"], len(expected))
                    evidence["actual"] = actual.hex()
                    if actual != expected:
                        raise AssertionError(
                            f"{arg['space']}[{arg['address']:#x}]: expected {expected.hex()}, got {actual.hex()}"
                        )
                elif op == "key":
                    fields(arg, ("code", "down"))
                    code = integer(arg["code"], 0, 255)
                    if type(arg["down"]) is not bool:
                        raise ValueError("key down must be boolean")
                    runtime.checked("dac_key", code, arg["down"])
                elif op == "reset" and arg is True:
                    runtime.reset()
                else:
                    raise ValueError(f"unsupported operation: {op}")
                evidence["state"] = runtime.observe()
                evidence["epoch"] = runtime.epoch
                if time.monotonic() >= deadline:
                    raise TimeoutError("wall-clock limit exceeded")
        finally:
            events.extend(runtime.events)
            report["trace_complete"] = not runtime.overflow


def run_file(scenario, library, output, wall_timeout=30):
    if not 0 < wall_timeout <= 3600:
        raise ValueError("wall timeout must be positive and <=3600 seconds")
    scenario, library, output = map(Path, (scenario, library, output))
    output.mkdir(parents=True, exist_ok=False)
    report = {"schema": "dac-verification-1", "verdict": "fail"}
    events = []
    try:
        raw = scenario.read_bytes()
        if len(raw) > 1048576:
            raise ValueError("scenario exceeds 1 MiB")
        report.update(
            scenario_sha256=sha(raw), runtime_sha256=sha(library.read_bytes())
        )
        execute(
            json.loads(raw),
            scenario.resolve().parent,
            library,
            report,
            events,
            wall_timeout,
        )
        report["verdict"] = "pass"
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        RuntimeError,
        AssertionError,
    ) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    report["events"] = len(events)
    with (output / "trace.jsonl").open("w") as stream:
        header = {
            "schema": "dac-trace-1",
            "machine": report.get("machine"),
            "enabled": report.get("trace_enabled", False),
            "complete": report.get("trace_complete", False),
            "inputs": report.get("inputs"),
            "profile": report.get("profile"),
        }
        stream.write(json.dumps(header, sort_keys=True) + "\n")
        for event in events:
            stream.write(json.dumps(event, sort_keys=True) + "\n")
    report["trace_sha256"] = sha((output / "trace.jsonl").read_bytes())
    (output / "report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", type=Path)
    parser.add_argument(
        "--library", type=Path, default=ROOT / "build/libdac-runtime.so"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="new artifact directory"
    )
    parser.add_argument("--wall-timeout", type=float, default=30)
    args = parser.parse_args()
    try:
        report = run_file(args.scenario, args.library, args.output, args.wall_timeout)
    except (ValueError, OSError) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(report, sort_keys=True))
    return 0 if report["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
