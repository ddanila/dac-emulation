"""Compare complete access traces, reporting the first divergence and context."""

import argparse
import json
from itertools import zip_longest
from pathlib import Path


def read_trace(path):
    with Path(path).open() as stream:
        header = json.loads(next(stream))
        if (
            header.get("schema") != "dac-trace-1"
            or header.get("complete") is not True
            or header.get("enabled") is not True
        ):
            raise ValueError(
                "comparison requires an enabled, complete dac-trace-1 capture"
            )
        if (
            not isinstance(header.get("machine"), str)
            or not isinstance(header.get("inputs"), dict)
            or not isinstance(header.get("profile"), dict)
        ):
            raise TypeError("missing machine, inputs or stepping profile")
        events = [json.loads(line) for line in stream]
    if not events:
        raise ValueError("empty traces cannot establish agreement")
    for event in events:
        if event.get("kind") not in ("MR", "MW", "IR", "IW", "IA"):
            raise ValueError("unknown access kind")
        for name in (
            "epoch",
            "address",
            "data",
            "cycle",
            "source",
            "master",
            "space",
            "offset",
        ):
            if type(event.get(name)) is not int or event[name] < 0:
                raise ValueError(f"invalid event field {name}")
        if event["data"] > 255 or event["master"] not in (0, 1) or event["space"] > 5:
            raise ValueError("invalid data, master or address space")
    return header, events


def compare(left_path, right_path, mode="ordered"):
    if mode not in ("ordered", "mapped", "timed"):
        raise ValueError("mode must be ordered, mapped or timed")
    left_header, left = read_trace(left_path)
    right_header, right = read_trace(right_path)
    for name in ("machine", "inputs"):
        if left_header[name] != right_header[name]:
            raise ValueError(
                f"trace {name} differ; establish equivalent inputs explicitly"
            )
    if mode == "timed" and (
        not left_header["profile"].get("clock_hz")
        or left_header["profile"] != right_header["profile"]
    ):
        raise ValueError(
            "timed comparison requires matching clock and stepping contracts"
        )

    def project(event):
        if event is None:
            return None
        # Interrupt-acknowledge bus addresses are not meaningful.
        result = [event[n] for n in ("epoch", "kind", "source", "master")]
        result += [None if event["kind"] == "IA" else event["address"], event["data"]]
        if mode == "mapped" and event["kind"] in ("MR", "MW"):
            if not event["space"]:
                raise ValueError("mapped comparison requires resolved memory spaces")
            result += [event["space"], event["offset"]]
        if mode == "timed":
            result += [event["cycle"]]
        return result

    for index, (a, b) in enumerate(zip_longest(left, right)):
        if project(a) != project(b):
            return {
                "verdict": "fail",
                "mode": mode,
                "index": index,
                "left": a,
                "right": b,
                "context_left": left[max(0, index - 3) : index + 4],
                "context_right": right[max(0, index - 3) : index + 4],
            }
    return {"verdict": "pass", "mode": mode, "events": len(left)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("left")
    parser.add_argument("right")
    parser.add_argument(
        "--mode", choices=("ordered", "mapped", "timed"), default="ordered"
    )
    args = parser.parse_args()
    try:
        result = compare(args.left, args.right, args.mode)
    except (ValueError, TypeError, KeyError, OSError, StopIteration) as error:
        parser.exit(2, f"{error}\n")
    print(json.dumps(result, indent=2))
    return 0 if result["verdict"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
