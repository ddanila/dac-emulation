"""Recheck the retained changing-input workload against the timed baseline."""
import hashlib
import json
import lzma
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE.parents[1] / 'latch-timing-envelope/firmware/firmware-hdl.txt.xz'

def sha(data):
    return hashlib.sha256(data).hexdigest()

def events(data):
    return [line for line in data.splitlines() if line.startswith((b'BIT ', b'LED ', b'EDGE '))]

baseline = lzma.decompress(BASELINE.read_bytes())
hdl = lzma.decompress((HERE / 'firmware-hdl.txt.xz').read_bytes())
report_bytes = (HERE / 'report.json').read_bytes()
report = json.loads(report_bytes)
assert report['equivalent']
assert report['floatingIoExperiment']['completeByteCoverage']
assert events(hdl) and events(hdl) == events(baseline)
result = {
    'passed': True,
    'qualified': False,
    'baseline': str(BASELINE.relative_to(HERE.parents[1])),
    'baselineHdlLogSha256': sha(baseline),
    'hdlLogSha256': sha(hdl),
    'reportSha256': sha(report_bytes),
    'eventsEqualBaselineValuesAndCycles': True,
    'eventCount': len(events(hdl)),
    'boundary': 'One deterministic changing-byte sequence on released reads, with reference ROM/latch timing envelopes. Not exhaustive input-sequence or internal-state equivalence, metastability, or electrical qualification.',
}
if __name__ == '__main__':
    print(json.dumps(result, indent=2))
