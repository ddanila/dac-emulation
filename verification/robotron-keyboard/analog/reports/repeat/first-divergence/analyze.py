"""Inspect the archived first repeat-timing failure without qualifying its runs."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
assessment = json.loads((HERE / 'assessment.json').read_text())
first = assessment['comparison']['firstTimingDifference']
result = {'qualified': False, 'thresholdVolts': 1.4, 'samples': {}}
for kind in ('coarse', 'fine'):
    path = HERE / (kind + '-window.txt')
    rows = [[float(v) for v in line.split()] for line in path.read_text().splitlines()[1:]]
    crossings = [(a,b) for a,b in zip(rows, rows[1:]) if a[2] < 1.4 <= b[2]]
    assert len(crossings) == 1
    a,b = crossings[0]
    crossing = a[0] + (1.4-a[2])*(b[0]-a[0])/(b[2]-a[2])
    observed = first[kind+'EventTimePs'] * 1e-12
    result['samples'][kind] = {
        'windowSha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'risingCrossingBracket': [a,b],
        'bracketWidthNs': (b[0]-a[0])*1e9,
        'linearCrossingEstimateSeconds': crossing,
        'recordedReceiverTimeSeconds': observed,
        'recordedMinusUpperSampleNs': (observed-b[0])*1e9,
        'recordedMinusLinearEstimateNs': (observed-crossing)*1e9,
    }
a,b = result['samples'].values()
result['linearCrossingEstimateDifferenceNs'] = abs(a['linearCrossingEstimateSeconds']-b['linearCrossingEstimateSeconds'])*1e9
result['boundary'] = 'Linear interpolation is descriptive, not a replacement for the recorded HDL receiver event or the 15 ns acceptance gate. Original time-order diagnostics remain unresolved. Printed waveform precision limits these estimates.'
print(json.dumps(result, indent=2))
