#!/usr/bin/env python3
"""Check native binary output and FIFO transport against a complete RC control."""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
from compressed_output import capture
from raw_waveform import header, rows
from trace_io import open_binary

DECK = '''Raw-output transport control
V1 in 0 PULSE(0 5 1n 1n 1n 10n 20n)
R1 in out 1k
C1 out 0 1p
.save v(in) v(out) i(V1)
.tran .1n 100n
.control
set filetype=binary
set wr_vecnames
set wr_singlescale
set numdgt=17
{commands}
quit
.endc
.end
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def review(original, candidate, out):
    out.mkdir(parents=True, exist_ok=False)
    receipts, samples = {}, {}
    for name, runtime, mode in [('memory', original, 'memory'),
                                ('original-file', original, 'file'),
                                ('candidate-file', candidate, 'file'),
                                ('candidate-pipe', candidate, 'pipe')]:
        directory = out/name
        directory.mkdir()
        commands = 'run\nwrdata trace.txt v(in) v(out) i(V1)' if mode == 'memory' else 'run trace.raw'
        (directory/'io.cir').write_text(DECK.format(commands=commands))
        with capture(directory, ['trace.raw'], enabled=mode == 'pipe') as storage:
            with (directory/'ngspice.log').open('w') as log:
                result = subprocess.run([str(runtime), '-n', '-b', 'io.cir'], cwd=directory,
                                        env=os.environ.copy(), stdout=log, stderr=subprocess.STDOUT, timeout=30)
            if result.returncode:
                raise ValueError('Failed transport control')
        log = (directory/'ngspice.log').read_text()
        counts = re.findall(r'No\. of Data Rows\s*:\s*(\d+)', log)
        if len(counts) != 1:
            raise ValueError('Missing unique completion count')
        count = int(counts[0])
        if mode == 'memory':
            lines = (directory/'trace.txt').read_text().splitlines()
            names = lines[0].split()
            data = [tuple(map(float, line.split())) for line in lines[1:]]
        else:
            with open_binary(directory/'trace.raw') as stream:
                names, declared = header(stream)
                if declared != (0 if mode == 'pipe' else count):
                    raise ValueError('Unexpected raw header count')
                data = list(rows(stream, len(names), count))
        if len(data) != count or data[0][0] != 0 or abs(data[-1][0]-1e-7) > 2*math.ulp(1e-7):
            raise ValueError('Incomplete control window')
        normalized = {n.lower(): [row[i] for row in data] for i,n in enumerate(names)}
        samples[name] = normalized
        receipts[name] = {'samples': count, 'storage': storage, 'runtimeSha256': sha(runtime),
                          'deckSha256': sha(directory/'io.cir')}
    if any(value != samples['memory'] for value in samples.values()):
        raise ValueError('Transport changes samples')
    report = {'allSamplesExactlyEqual': True, 'runs': receipts,
              'qualified': False, 'boundary': 'RC transport control only; live coupled control and full-repeat qualification remain required.'}
    (out/'assessment.json').write_text(json.dumps(report, indent=2)+'\n')
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--original', type=Path)
    p.add_argument('--candidate', type=Path)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--check', action='store_true')
    a = p.parse_args()
    if a.check:
        manifest = json.loads((a.out/'manifest.json').read_text())
        actual = {str(f.relative_to(a.out)): sha(f) for f in a.out.rglob('*')
                  if f.is_file() and f.name != 'manifest.json'}
        if actual != manifest:
            raise ValueError('Changed or missing retained transport evidence')
    else:
        if not a.original or not a.candidate:
            p.error('--original and --candidate are required for a new control')
        review(a.original.resolve(), a.candidate.resolve(), a.out)
