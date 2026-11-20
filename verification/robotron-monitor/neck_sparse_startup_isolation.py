"""Audit whether the SSY20A parameter additions cause the sparse startup stop.

The comparison replaces only the SSY20A model declaration in an otherwise
identical current connected deck. Both runs are diagnostics, not field scores.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct


ROOT = Path(__file__).resolve().parent
MODEL = ROOT/'circuits/k7222-11-neck-models.cir'
STEADY = ROOT/'steady_supply.py'
TRANSIENT_REPORT = ROOT/'reference/k7222-11/page3-4-connected-contrast-transient.json'
OLD_MODEL = ('.model SSY20A_BOUND NPN(IS={q_is} BF={q_bf} VAF={q_vaf}\n'
             '+ TF={q_tf} TR={q_tr} CJE={q_cje} CJC={q_cjc})\n')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def model_declaration(path):
    text = Path(path).read_text()
    match = re.search(r'(?m)^\.model SSY20A_BOUND NPN\([^)]*\)\n', text)
    if not match:
        raise ValueError('SSY20A declaration missing')
    return match.group()


def raw_tail(path):
    with Path(path).open('rb') as stream:
        header = b''
        while not header.endswith(b'Binary:\n'):
            line = stream.readline()
            if not line or len(header) > 1_000_000:
                raise ValueError('missing raw header')
            header += line
        count = int(re.search(rb'No. Variables:\s+(\d+)', header)[1])
        row_size = count*8
        start = stream.tell()
        stream.seek(0, 2)
        length = stream.tell()-start
        if length < 2*row_size or length % row_size:
            raise ValueError('invalid raw trace length')
        rows = length//row_size
        stream.seek(start+(rows-1)*row_size)
        last_time = struct.unpack('=d', stream.read(8))[0]
        return rows, last_time


def case(directory):
    directory = Path(directory)
    log = (directory/'solver.log').read_text(errors='replace')
    errors = [line.strip() for line in log.replace('\r', '\n').splitlines()
              if 'Timestep too small' in line]
    rows, last = raw_tail(directory/'trace.raw')
    if len(errors) != 1 or not 46.295e-6 <= last <= 46.297e-6:
        raise ValueError('startup result changed')
    return {'deck_sha256': sha(directory/'run.cir'),
            'raw_sha256': sha(directory/'trace.raw'),
            'log_sha256': sha(directory/'solver.log'),
            'complete_rows': rows, 'last_time_s': last,
            'solver_error': errors[0]}


def summarize(new_directory, old_directory):
    new_directory = Path(new_directory)
    old_directory = Path(old_directory)
    new_text = (new_directory/'run.cir').read_text()
    old_text = (old_directory/'run.cir').read_text()
    active = model_declaration(MODEL)
    if new_text.count(active) != 1 or old_text != new_text.replace(active, OLD_MODEL):
        raise ValueError('decks differ beyond the SSY20A declaration')
    current = json.loads(TRANSIENT_REPORT.read_text())
    detailed = next(row for row in current['rows'] if row['case'] == 'detailed_sparse')
    if (current['steady_supply_sha256'] != sha(STEADY) or
            detailed['short_deck_sha256'] != sha(new_directory/'run.cir') or
            detailed['completed']):
        raise ValueError('current connected startup receipt changed')
    return {'format': 'dac-monitor-neck-sparse-startup-isolation-v1',
            'qualification': 'one-declaration solver diagnostic, no connected field or model qualification',
            'source_sha256': {'producer': sha(ROOT/'neck_sparse_startup_isolation.py'),
                              'steady_supply': sha(STEADY), 'neck_model': sha(MODEL),
                              'current_startup_receipt': sha(TRANSIENT_REPORT)},
            'old_model_declaration': OLD_MODEL.strip(),
            'current_model_declaration': active.strip(),
            'new_model': case(new_directory),
            'previous_model_declaration': case(old_directory),
            'inference': ('Both otherwise identical current connected decks stop at the first BSYN event. '
                          'The SSY20A additions are not necessary for this sparse-solver failure; '
                          'the earlier completed receipt came from a different runner revision.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--new-directory', type=Path, required=True)
    parser.add_argument('--old-directory', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    a.output.write_text(json.dumps(summarize(a.new_directory, a.old_directory),
                                   indent=2)+'\n')
