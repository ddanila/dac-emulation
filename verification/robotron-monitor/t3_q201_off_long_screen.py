"""Extend the diagnostic Q201-off connected deck to four native field periods.

Q201 is not removed from the accepted circuit. This only tests whether the
39 ms stop is the last numerical obstacle in that conditional T3 run.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import struct

import steady_supply
import t3_field_boundary_screen as boundary
import t3_input_boundary_isolation as isolation


ROOT = Path(__file__).resolve().parent
SHORT = '.tran 5e-08 0.0391 0 5e-08'
FOUR = '.tran 5e-08 0.078 0 5e-08'
FIELD_S = .0195


def below_duration(left, right, first, second, limit):
    """Duration below a limit for a linearly interpolated voltage segment."""
    if first < limit and second < limit:
        return right-left
    if first >= limit and second >= limit:
        return 0.
    crossing = left+(limit-first)*(right-left)/(second-first)
    return crossing-left if first < limit else right-crossing


def summarize_raw(path):
    """Read complete real rows, allowing zero-duration solver event pairs."""
    digest = hashlib.sha256()
    fields = [dict(index=i+1, rows=0, duration_s=0., eht_volt_seconds=0.,
                   eht_min_v=float('inf'), eht_max_v=-float('inf'),
                   h_sync_min_v=float('inf'), h_sync_max_v=-float('inf'),
                   h_hot_peak_v=-float('inf'),
                   v18_base_min_v=float('inf'), v18_base_max_v=-float('inf'),
                   v18_base_below_minus_9v_duration_s=0.,
                   h_hot_upcrossings_100v=0) for i in range(4)]
    previous = None
    rows = duplicates = trailing = 0
    with Path(path).open('rb') as stream:
        header = b''
        while not header.endswith(b'Binary:\n'):
            line = stream.readline()
            if not line or len(header) > 1_000_000:
                raise ValueError('missing real raw header')
            digest.update(line)
            header += line
        if b'Flags: real' not in header:
            raise ValueError('expected real ngspice raw trace')
        count = int(re.search(rb'No. Variables:\s+(\d+)', header)[1])
        declared = int(re.search(rb'No. Points:\s+(\d+)', header)[1])
        names = [name.decode() for name in re.findall(
            rb'^\s*\d+\s+(\S+)\s+\S+\s*$',
            header.split(b'Variables:\n')[1].split(b'Binary:')[0], re.M)]
        if len(names) != count or names[0] != 'time':
            raise ValueError('invalid raw variable table')
        indices = [names.index(name) for name in
                   ('v(eht)', 'v(h_sync)', 'v(h_hot)',
                    'v(h_outputbase)')]
        unpack = struct.Struct('='+str(count)+'d')
        while data := stream.read(unpack.size):
            digest.update(data)
            if len(data) != unpack.size:
                trailing = len(data)
                break
            values = unpack.unpack(data)
            if not all(map(math.isfinite, values)):
                raise ValueError('nonfinite raw sample')
            t = values[0]
            eht, sync, hot, base = (values[i] for i in indices)
            if t < 0 or (previous is not None and t < previous[0]):
                raise ValueError('backward raw time')
            if previous is not None and t == previous[0]:
                duplicates += 1
            slot = min(int(t/FIELD_S), 3)
            field = fields[slot]
            field['rows'] += 1
            field['eht_min_v'] = min(field['eht_min_v'], eht)
            field['eht_max_v'] = max(field['eht_max_v'], eht)
            field['h_sync_min_v'] = min(field['h_sync_min_v'], sync)
            field['h_sync_max_v'] = max(field['h_sync_max_v'], sync)
            field['h_hot_peak_v'] = max(field['h_hot_peak_v'], hot)
            field['v18_base_min_v'] = min(field['v18_base_min_v'], base)
            field['v18_base_max_v'] = max(field['v18_base_max_v'], base)
            if previous is not None:
                t0, e0, _, h0, b0 = previous
                if h0 < 100 <= hot:
                    fields[min(int(t/FIELD_S), 3)]['h_hot_upcrossings_100v'] += 1
                left = t0
                while left < t:
                    part = min(int(left/FIELD_S), 3)
                    right = min(t, (part+1)*FIELD_S)
                    if right <= left:
                        right = t
                    el = e0+(eht-e0)*(left-t0)/(t-t0)
                    er = e0+(eht-e0)*(right-t0)/(t-t0)
                    bl = b0+(base-b0)*(left-t0)/(t-t0)
                    br = b0+(base-b0)*(right-t0)/(t-t0)
                    fields[part]['eht_volt_seconds'] += (el+er)*(right-left)/2
                    fields[part]['duration_s'] += right-left
                    fields[part]['v18_base_below_minus_9v_duration_s'] += (
                        below_duration(left, right, bl, br, -9.))
                    left = right
            previous = (t, eht, sync, hot, base)
            rows += 1
    if rows < 2:
        raise ValueError('trace lacks complete rows')
    for field in fields:
        field['eht_time_mean_v'] = (field.pop('eht_volt_seconds')/field['duration_s']
                                    if field['duration_s'] else None)
        field['tp17_mapped_swing_vpp'] = (field['h_sync_max_v']-field['h_sync_min_v']
                                         if field['rows'] else None)
        if not field['rows']:
            for name in ('eht_min_v', 'eht_max_v', 'h_sync_min_v',
                         'h_sync_max_v', 'h_hot_peak_v', 'v18_base_min_v',
                         'v18_base_max_v'):
                field[name] = None
    return {'sha256': digest.hexdigest(), 'declared_points': declared,
            'complete_rows': rows, 'trailing_bytes': trailing,
            'equal_time_event_rows': duplicates,
            'last_time_s': previous[0], 'fields': fields}


def summarize(short_directory, long_directory, runtime, timeout_s):
    short_directory = Path(short_directory)
    long_directory = Path(long_directory)
    prior = json.loads((ROOT/'reference/k7222-11/t3-horizontal-boundary-isolation.json').read_text())
    short_deck = short_directory/'run.cir'
    saved = next(case for case in prior['cases'] if case['name'] == 'q201_off')
    if (boundary.sha(short_deck) != saved['deck_sha256'] or
            short_deck.read_text().count(SHORT) != 1 or
            short_deck.read_text().count('R201_off contrast_low 0 1G') != 1):
        raise ValueError('Q201-off short deck differs from archived case')
    deck = short_deck.read_text().replace(SHORT, FOUR)
    if long_directory.exists():
        if (long_directory/'run.cir').read_text() != deck:
            raise ValueError('existing long deck differs beyond endpoint')
        solve = json.loads((long_directory/'solve.json').read_text())
    else:
        solve = steady_supply.solve(deck, long_directory, runtime,
                                    timeout_s=timeout_s)
    raw = long_directory/'trace.raw'
    trace = summarize_raw(raw)
    last = trace['last_time_s']
    sample_times = {f'field_{i}': FIELD_S*i for i in range(1, 5)
                    if FIELD_S*i <= last+1e-12}
    samples, _ = isolation.raw_samples(raw, sample_times,
                                       ('v(eht)', 'v(h_hot)', 'v(h_sync)',
                                        'v(cathode)'))
    log = (long_directory/'solver.log').read_text(errors='replace')
    eht_means = [field['eht_time_mean_v'] for field in trace['fields']]
    late_means = [value for value in eht_means[1:] if value is not None]
    return {
        'format': 'dac-monitor-t3-q201-off-long-screen-v3',
        'qualification': 'conditional T3 / manual-Fig-6 contrast diagnostic with Q201 removed; no source-circuit, periodicity or A5 qualification',
        'source_sha256': {name: boundary.sha(ROOT/name) for name in
                          ('t3_q201_off_long_screen.py', 'steady_supply.py')},
        'short_deck_sha256': saved['deck_sha256'],
        'long_deck_sha256': boundary.sha(long_directory/'run.cir'),
        'only_change_from_short_deck': 'transient endpoint 39.1 ms to 78 ms',
        'solver': {'status': solve['status'], 'elapsed_s': solve['elapsed_s'],
                   'timeout': solve['timeout'],
                   'runtime_archive_sha256': solve['runtime']['archive_sha256'],
                   'runtime_binary_sha256': solve['runtime']['files']['install/bin/ngspice'],
                   'log_sha256': boundary.sha(long_directory/'solver.log'),
                   'abort_messages': [line.strip() for line in log.replace('\r', '\n').splitlines()
                                      if 'Timestep too small' in line or
                                      'run simulation(s) aborted' in line]},
        'trace': trace,
        'four_fields_completed': (solve['status'] == 'complete' and
                                  last >= 4*FIELD_S-1e-10 and
                                  trace['complete_rows'] == trace['declared_points'] and
                                  trace['trailing_bytes'] == 0 and
                                  all(abs(field['duration_s']-FIELD_S) < 1e-9
                                      for field in trace['fields'])),
        'diagnostic_metrics': {
            'last_three_eht_mean_spread_fraction': ((max(late_means)-min(late_means)) /
                                                    (sum(late_means)/len(late_means))
                                                    if len(late_means) == 3 else None),
            'fourth_field_eht_entirely_below_11kv': (
                trace['fields'][3]['eht_max_v'] < 11000
                if trace['fields'][3]['rows'] else None),
            'h_hot_upcrossings_100v_by_field': [field['h_hot_upcrossings_100v']
                                                for field in trace['fields']],
            'v18_reverse_base_9v_class_comparator': {
                'basis': 'BU508AF-class reverse emitter-base absolute maximum; not a rating for the unidentified original V18',
                'limit_v': -9.,
                'below_limit_duration_s_by_field': [
                    field['v18_base_below_minus_9v_duration_s']
                    for field in trace['fields']],
            },
        },
        'field_boundary_samples': samples,
        'interpretation': 'A Q201-off solve can locate later connected numerical stops, but its transistor removal and conditional T3/contrast topology cannot qualify a source-circuit operating point.',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--short-directory', type=Path, required=True)
    parser.add_argument('--long-directory', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--timeout-s', type=float, default=1200)
    args = parser.parse_args()
    args.report.write_text(json.dumps(summarize(args.short_directory,
                                                args.long_directory,
                                                args.runtime,
                                                args.timeout_s), indent=2)+'\n')
    print(args.report)
