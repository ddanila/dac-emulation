"""Bounded startup solver screen for the conditional manual contrast equivalent.

This uses native logical input and the complete ideal-rail assembly, but stops
after 200 us. It tests numerical feasibility, not a sustained monitor state.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import steady_supply
import transformer_candidates


ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT/'examples/phase-a-native-full-text'
CANDIDATE_ID = 't3-fc941ad61c50ce31'
END_S = 200e-6
CASES = (
    ('detailed_sparse', 'detailed-page3-4', {}),
    ('manual_sparse', 'manual-fig6-equivalent', {}),
    ('manual_klu_tight', 'manual-fig6-equivalent',
     {'linear_solver': 'klu', 'max_step_s': 50e-9,
      'reltol': .002, 'abstol': 1e-8}),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def run():
    manifest = json.loads((ARCHIVE/'manifest.json').read_text())
    compressed = (ARCHIVE/'capture.json.gz').read_bytes()
    raw = gzip.decompress(compressed)
    if (sha(compressed) != manifest['compressed_sha256']
            or sha(raw) != manifest['capture_sha256']):
        raise ValueError('native capture archive hash changed')
    selection = steady_supply.select(json.loads(raw))
    if selection['status'] != 'complete':
        raise ValueError('native capture lacks a repeated complete field')
    rows = []
    with tempfile.TemporaryDirectory() as temporary:
        folder = Path(temporary)
        assembly = steady_supply.assemble(folder/'assembly')
        steady_supply.tune(assembly, selection)
        candidates = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])
        candidate = next((item for item in candidates if item['id'] == CANDIDATE_ID), None)
        if candidate is None:
            raise ValueError('screened T3 sign candidate changed')
        for label, topology, solver in CASES:
            assembly['contrast_topology'] = topology
            deck, metadata = steady_supply.deck(assembly, selection, candidate, **solver)
            if metadata['contrast_topology'] != topology:
                raise ValueError('deck topology metadata differs from selection')
            short_deck, count = re.subn(r'^\.tran .*$',
                '.tran 100n 200u 0 100n', deck, flags=re.MULTILINE)
            if count != 1:
                raise ValueError('connected deck lacks a unique transient command')
            trial = folder/label
            trial.mkdir()
            (trial/'run.cir').write_text(short_deck)
            try:
                result = subprocess.run(['ngspice', '-b', '-r', 'trace.raw', 'run.cir'],
                                        cwd=trial, text=True, capture_output=True,
                                        timeout=30)
                log = result.stdout+'\n'+result.stderr
                match = re.search(r'No\. of Data Rows\s*:\s*(\d+)', log)
                error = next((line.strip() for line in log.splitlines()
                              if 'Timestep too small' in line), None)
                trace = trial/'trace.raw'
                last = None
                if trace.is_file():
                    for point in steady_supply.raw_rows(trace):
                        last = point
                last_time = None if last is None else last['time']
                rows.append(dict(case=label, contrast_topology=topology,
                                 solver=metadata['linear_solver'],
                                 reltol=metadata['reltol'], abstol=metadata['abstol'],
                                 max_step_s=metadata['max_step_s'],
                                 short_deck_sha256=sha(short_deck.encode()),
                                 returncode=result.returncode,
                                 completed=(result.returncode == 0 and error is None
                                            and match is not None and last_time is not None
                                            and last_time >= END_S-1e-12),
                                 data_rows=int(match.group(1)) if match else None,
                                 last_time_s=last_time,
                                 last_cathode_v=None if last is None else last.get('v(cathode)'),
                                 last_eht_v=None if last is None else last.get('v(eht)'),
                                 timestep_failure=error))
            except subprocess.TimeoutExpired:
                rows.append(dict(case=label, contrast_topology=topology,
                                 solver=metadata['linear_solver'],
                                 reltol=metadata['reltol'], abstol=metadata['abstol'],
                                 max_step_s=metadata['max_step_s'],
                                 short_deck_sha256=sha(short_deck.encode()),
                                 returncode=None, completed=False,
                                 data_rows=None, last_time_s=None,
                                 last_cathode_v=None, last_eht_v=None,
                                 timestep_failure='30 s timeout'))
        hashes = assembly['hashes']
    return dict(format='dac-monitor-page3-4-connected-contrast-transient-v1',
                qualification='200 us startup solver screen with native logical input; not a complete field, sustained-state score, calibration or factory topology proof',
                archive_capture_sha256=sha(raw),
                selected_field_content_sha256=selection['source_content_sha256'],
                selection_period_s=selection['period_ticks']/selection['clock_hz'],
                candidate_id=CANDIDATE_ID,
                candidate_qualification='unverified T3 winding graph and sign candidate',
                steady_supply_sha256=sha((ROOT/'steady_supply.py').read_bytes()),
                assembly_hashes=hashes,
                tested_duration_s=END_S,
                rows=rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('short connected trials:', [(row['case'], row['completed'])
                                     for row in report['rows']])
