import copy
import json
import tempfile
import unittest
from pathlib import Path

from verification.compare import compare
from verification.runtime import Runtime
from verification.scenario import ROOT, run_file

LIBRARY = ROOT / "build/libdac-runtime.so"


class Scenarios(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.counter = 0

    def document(self, machine):
        return json.loads(
            (ROOT / f"examples/scenarios/{machine}-memory.json").read_text()
        )

    def run_document(self, document):
        self.counter += 1
        path = self.root / f"scenario-{self.counter}.json"
        path.write_text(json.dumps(document))
        output = self.root / f"result-{self.counter}"
        return run_file(path, LIBRARY, output), output

    def test_both_machines_deterministic_reset_and_memory_conditions(self):
        for machine in ("juku", "robotron"):
            with self.subTest(machine=machine):
                doc = self.document(machine)
                first, a = self.run_document(doc)
                second, b = self.run_document(doc)
                self.assertEqual(first["verdict"], "pass", first)
                self.assertEqual(first, second)
                self.assertEqual(
                    compare(a / "trace.jsonl", b / "trace.jsonl", "timed")["verdict"],
                    "pass",
                )
                self.assertEqual(first["steps"][0]["stop"], "condition")
                self.assertEqual(first["steps"][-1]["epoch"], 1)
                if machine == "robotron":
                    self.assertEqual(
                        compare(a / "trace.jsonl", b / "trace.jsonl", "mapped")[
                            "verdict"
                        ],
                        "pass",
                    )

    def test_unreachable_condition_and_bad_memory_have_failure_evidence(self):
        for machine in ("juku", "robotron"):
            for fault in (
                "unreachable",
                "range",
                "space",
                "operation",
                "bool-budget",
                "overflow",
            ):
                with self.subTest(machine=machine, fault=fault):
                    doc = self.document(machine)
                    if fault == "unreachable":
                        doc["steps"][0]["until"]["hex"] = "43"
                    elif fault == "range":
                        doc["steps"][0]["until"]["address"] = 0xFFFFFFFF
                    elif fault == "space":
                        doc["steps"][0]["until"]["space"] = "io"
                    elif fault == "operation":
                        doc["steps"] = [{"unsupported": 1}]
                    elif fault == "bool-budget":
                        doc["steps"] = [{"run": True}]
                    else:
                        doc["trace_limit"] = 1
                    report, output = self.run_document(doc)
                    self.assertEqual(report["verdict"], "fail")
                    self.assertIn("error", report)
                    self.assertTrue((output / "report.json").is_file())
                    if fault == "overflow":
                        self.assertFalse(report["trace_complete"])
                        with self.assertRaises(ValueError):
                            compare(output / "trace.jsonl", output / "trace.jsonl")

    def test_instruction_overshoot_and_tick_exactness_are_reported(self):
        for machine in ("juku", "robotron"):
            doc = self.document(machine)
            doc["steps"] = [{"run": 1}]
            report, _ = self.run_document(doc)
            advanced = report["steps"][0]["advanced"]
            self.assertGreater(advanced, 1) if machine == "juku" else self.assertEqual(
                advanced, 1
            )

    def test_observation_does_not_advance_or_emit_bus_events(self):
        for machine in ("juku", "robotron"):
            doc = self.document(machine)
            with Runtime(LIBRARY, doc["machine"], 1000) as runtime:
                for slot, spec in doc["firmware"].items():
                    runtime.load(
                        int(slot), bytes.fromhex(spec["hex"]).ljust(spec["size"], b"\0")
                    )
                runtime.power()
                runtime.run(50)
                before, events = runtime.observe(), copy.deepcopy(runtime.events)
                self.assertEqual(runtime.peek("ram", 0x8000, 1), b"B")
                self.assertEqual(runtime.observe(), before)
                self.assertEqual(runtime.events, events)
                with self.assertRaises(RuntimeError):
                    runtime.peek("ram", 262144, 1)

    def test_first_divergence_length_and_timing_modes(self):
        _, a = self.run_document(self.document("robotron"))
        source = (a / "trace.jsonl").read_text().splitlines()
        other = self.root / "changed.jsonl"
        modified = list(source)
        event = json.loads(modified[3])
        event["cycle"] += 1
        modified[3] = json.dumps(event)
        other.write_text("\n".join(modified) + "\n")
        self.assertEqual(compare(a / "trace.jsonl", other)["verdict"], "pass")
        self.assertEqual(compare(a / "trace.jsonl", other, "timed")["index"], 2)
        event["data"] ^= 1
        modified[3] = json.dumps(event)
        other.write_text("\n".join(modified) + "\n")
        result = compare(a / "trace.jsonl", other)
        self.assertEqual(result["index"], 2)
        self.assertTrue(result["context_left"])
        other.write_text("\n".join(source[:-1]) + "\n")
        self.assertEqual(compare(a / "trace.jsonl", other)["index"], len(source) - 2)

    def test_mapping_master_and_missing_timing_are_not_silently_ignored(self):
        _, output = self.run_document(self.document("robotron"))
        records = [
            json.loads(line)
            for line in (output / "trace.jsonl").read_text().splitlines()
        ]
        other = self.root / "mapped.jsonl"
        records[1]["offset"] += 1
        other.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        self.assertEqual(compare(output / "trace.jsonl", other)["verdict"], "pass")
        self.assertEqual(compare(output / "trace.jsonl", other, "mapped")["index"], 0)
        records[1]["master"] = 1
        other.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        self.assertEqual(compare(output / "trace.jsonl", other)["index"], 0)
        records[0]["profile"]["clock_hz"] = None
        other.write_text("\n".join(json.dumps(r) for r in records) + "\n")
        with self.assertRaises(ValueError):
            compare(other, other, "timed")

    def test_disabled_traces_and_existing_outputs_are_rejected(self):
        doc = self.document("juku")
        doc.pop("trace_limit")
        report, output = self.run_document(doc)
        self.assertEqual(report["verdict"], "pass")
        with self.assertRaises(ValueError):
            compare(output / "trace.jsonl", output / "trace.jsonl")
        with self.assertRaises(FileExistsError):
            run_file(ROOT / "examples/scenarios/juku-memory.json", LIBRARY, output)
