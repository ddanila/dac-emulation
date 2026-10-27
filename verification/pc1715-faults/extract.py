#!/usr/bin/env python3
"""Extract bounded, independently hashed observations from MB001 .lac.gz files."""
import argparse
import base64
import bisect
import gzip
import hashlib
import json
from pathlib import Path

RUNS = ["20261027-reset-release", "20261027-reset-release-repeat",
        "20261027-reset-release-third", "20261027-reset-release-fourth",
        "20261027-reset-release-fifth-valid", "20261027-reset-restored",
        "20261027-rom-controls"]


def low_windows(levels):
    start = None
    for i in range(1, len(levels)):
        if levels[i-1] and not levels[i]:
            start = i
        elif not levels[i-1] and levels[i] and start is not None:
            if i-start >= 7:
                yield start, i
            start = None


def extract(root, limit=128):
    result = dict(board="MB001", method="Complete /M1 and CPU /RD overlaps >=7 samples; "
                  "late bytes at end-2, secondary bytes at end-4; duration in measured "
                  "clock edges; additional CPU /RD pulses counted independently. "
                  "No absolute addresses or CPU-side data were captured.", runs=[])
    for name in RUNS:
        raw = gzip.decompress((root/name/"capture.lac.gz").read_bytes())
        s = json.loads(raw)["Settings"]
        a = {c["ChannelNumber"]: base64.b64decode(c["Samples"]) for c in s["CaptureChannels"]}
        size = len(a[0])
        assert s['Frequency'] == 25_000_000
        reset = [i for i in range(1, size) if a[10][i] > a[10][i-1]]
        assert len(reset) == 1
        clock = [i for i in range(1, size) if a[9][i] > a[9][i-1]]
        fetch = [(st, en) for st, en in low_windows(bytes(a[8][i] or a[11][i] for i in range(size))) if st > reset[0]]
        reads = list(low_windows(a[11]))
        read_starts = [st for st, en in reads]
        data = lambda i: sum(a[c][i] << bit for c, bit in enumerate([7,5,3,1,6,4,2,0]))
        rows = []
        for index, ((start, end), (nxt, _)) in enumerate(zip(fetch, fetch[1:])):
            if index == limit:
                break
            row = dict(data=data(end-2), data_minus4=data(end-4),
                       clocks=bisect.bisect_left(clock, nxt)-bisect.bisect_left(clock, start),
                       reads=bisect.bisect_left(read_starts, nxt)-bisect.bisect_right(read_starts, start))
            if 12 in a and 13 in a:
                row.update(ce=a[12][end-2], oe=a[13][end-2])
            rows.append(row)
        result['runs'].append(dict(name=name, capture_sha256=hashlib.sha256(raw).hexdigest(),
                                   sample_rate_hz=s['Frequency'], total_fetch_windows=len(fetch),
                                   first_fetch_delay_samples=fetch[0][0]-reset[0], fetches=rows))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(extract(args.evidence), indent=2)+'\n')
