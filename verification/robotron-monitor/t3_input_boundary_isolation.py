"""Archive the bounded input/contrast isolation of the 39 ms connected stop.

The isolated bench retains the captured input sources, S37 drivers, cable,
T200 gates and contrast devices, but substitutes fixed rails and simple loads
for the rest of the monitor. Crossing 39 ms there is a diagnostic, not a
connected field or an A3/A5 qualification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct

import t3_field_boundary_screen as boundary


ROOT = Path(__file__).resolve().parent
EXTRA_PROBES = ('v(base_i)', 'v(intensity_gate)', 'v(clamp_i)',
                'v(contrast_low)', 'v(intens)', 'v(rx_intens)', 'v(rx_bsyn)',
                'v(logic_intens)', 'v(logic_bsyn)', 'v(reference9)',
                'v(v1_base)', '@q201[ic]', '@q201[ib]')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def raw_samples(path, times, wanted):
    samples = {}
    with Path(path).open('rb') as stream:
        header = b''
        while not header.endswith(b'Binary:\n'):
            line = stream.readline()
            if not line or len(header) > 1_000_000:
                raise ValueError('missing raw header')
            header += line
        count = int(re.search(rb'No. Variables:\s+(\d+)', header)[1])
        names = [name.decode() for name in re.findall(
            rb'^\s*\d+\s+(\S+)\s+\S+\s*$',
            header.split(b'Variables:\n')[1].split(b'Binary:')[0], re.M)]
        if count != len(names) or names[0] != 'time':
            raise ValueError('invalid raw variable table')
        indices = {name: names.index(name) for name in wanted}
        row = struct.Struct('='+str(count)+'d')
        previous_time = -1.
        while data := stream.read(row.size):
            if len(data) != row.size:
                raise ValueError('truncated raw row')
            values = row.unpack(data)
            t = values[0]
            if t < previous_time:
                raise ValueError('nonmonotonic raw time')
            previous_time = t
            for label, target in times.items():
                if t <= target + 1e-12:
                    samples[label] = {'time_s': t, **{name: values[index]
                                                      for name, index in indices.items()}}
    return samples, previous_time


def solver(directory):
    directory = Path(directory)
    log = (directory/'solver.log').read_text(errors='replace')
    errors = [line.strip() for line in log.replace('\r', '\n').splitlines()
              if 'Timestep too small' in line]
    return {'returncode': int((directory/'returncode').read_text()),
            'deck_sha256': sha(directory/'run.cir'),
            'raw_sha256': sha(directory/'trace.raw'),
            'log_sha256': sha(directory/'solver.log'),
            'timestep_errors': errors}


def summarize(baseline, connected, isolated, dc_intens, bsyn_early):
    baseline, connected, isolated, dc_intens, bsyn_early = map(
        Path, (baseline, connected, isolated, dc_intens, bsyn_early))
    full = (baseline/'run.cir').read_text()
    short = boundary.shorten(full)
    modified = short.splitlines()
    save = [i for i, line in enumerate(modified) if line.startswith('.save ')]
    if len(save) != 1:
        raise ValueError('full deck lacks unique probe declaration')
    modified[save[0]] += ' '+' '.join(EXTRA_PROBES)
    if (connected/'run.cir').read_text() != '\n'.join(modified)+'\n':
        raise ValueError('connected probe deck differs from the baseline')
    dc = modified.copy()
    sources = [i for i, line in enumerate(dc) if line.startswith('Vlogic_intens ')]
    if len(sources) != 1 or not dc[sources[0]].endswith('PWL(0 1 0.0195 1) r=0'):
        raise ValueError('baseline INTENS source changed')
    dc[sources[0]] = 'Vlogic_intens logic_intens computer_return DC 1'
    dc[save[0]] = dc[save[0]].replace(' v(intens) v(rx_intens)',
                                      ' v(rx_intens)')
    dc[save[0]] = dc[save[0]].replace(' v(reference9) v(v1_base) @q201[ic] @q201[ib]', '')
    if (dc_intens/'run.cir').read_text() != '\n'.join(dc)+'\n':
        raise ValueError('DC INTENS trial differs beyond declared change and probes')
    edge = '0.0194999999 1 0.0195 0'
    if short.count(edge) != 1:
        raise ValueError('baseline final BSYN transition changed')
    early = short.replace(edge, '0.0194989999 1 0.019499 0 0.0195 0')
    if (bsyn_early/'run.cir').read_text() != early:
        raise ValueError('early BSYN trial differs beyond declared change')
    isolated_text = (isolated/'run.cir').read_text()
    for line in full.splitlines():
        if line.startswith(('Vlogic_', 'X101 ', 'X102 ', 'X103 ',
                            'Rwire_', 'Cwire_', 'X201 ', 'Q201 ', 'Q202 ',
                            'D204 ', 'D205 ', 'R208 ', 'R209 ', 'C201 ',
                            '.param gate_', '.param driver_',
                            '.model SC60A_CLASS_N', '.model SA20C_CLASS_N',
                            '.model Z9_BOUND', '.subckt S37_DRIVER',
                            '.subckt GATE', '.subckt T200_BOUND')):
            if line not in isolated_text.splitlines():
                raise ValueError('isolated input source or model differs: '+line[:60])
    connected_samples, connected_end = raw_samples(
        connected/'trace.raw', {'first_boundary': .0195,
                                'second_boundary': .039},
        ('v(base_i)', 'v(contrast_low)', 'v(intensity_gate)',
         'v(rx_bsyn)', 'v(h_hot)', 'v(eht)',
         'i(@q201[ic])', 'i(@q201[ib])'))
    isolated_samples, isolated_end = raw_samples(
        isolated/'trace.raw', {'after_boundary': .0391},
        ('v(base_i)', 'v(contrast_low)', 'v(intensity_gate)', 'v(rx_intens)'))
    dc_samples, dc_end = raw_samples(
        dc_intens/'trace.raw', {'first_boundary': .0195},
        ('v(base_i)', 'v(contrast_low)', 'v(intensity_gate)'))
    early_rows, early_end = boundary.raw_tail(bsyn_early/'trace.raw')
    if not (.038999999 <= connected_end <= .039000001 and
            isolated_end >= .0391-1e-10 and
            .019499999 <= dc_end <= .019500001 and
            .038999999 <= early_end <= .039000001):
        raise ValueError('diagnostic endpoints changed')
    return {
        'format': 'dac-monitor-t3-input-boundary-isolation-v1',
        'qualification': 'bounded solver diagnosis; isolated loads are surrogates, no connected field or service score',
        'source_sha256': {'producer': sha(ROOT/'t3_input_boundary_isolation.py'),
                          'boundary_screen': sha(ROOT/'t3_field_boundary_screen.py')},
        'baseline_deck_sha256': sha(baseline/'run.cir'),
        'connected_probes': {'solver': solver(connected),
                             'last_time_s': connected_end,
                             'samples': connected_samples},
        'isolated_input_contrast': {
            'scope': 'captured PWL sources, S37 drivers, cable, T200, page-3/4 contrast devices; fixed rails and surrogate external loads',
            'solver': solver(isolated), 'last_time_s': isolated_end,
            'samples': isolated_samples},
        'dc_intens_connected': {'change': 'constant captured INTENS PWL replaced by DC 1; same physical input level',
                                'solver': solver(dc_intens),
                                'last_time_s': dc_end, 'samples': dc_samples},
        'bsyn_early_connected': {'change': 'final BSYN falling edge moved 1 us earlier in every field; terminal 19.5 ms knot retained',
                                 'solver': solver(bsyn_early),
                                 'raw_complete_rows': early_rows,
                                 'last_time_s': early_end},
        'inference': ('The input/contrast subset crosses 39 ms with the captured repeated inputs and source drivers. '
                      'The full circuit fails with Q201 nearly static and off; this does not identify Q201 as the physical cause. '
                      'The DC INTENS variant fails earlier at the first field boundary and moving the final BSYN edge '
                      '1 us earlier still fails at 39 ms; neither is a solver remedy.'),
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'connected', 'isolated', 'dc-intens',
                 'bsyn-early', 'output'):
        parser.add_argument('--'+name, type=Path, required=True)
    a = parser.parse_args()
    a.output.write_text(json.dumps(summarize(a.baseline, a.connected,
                                            a.isolated, a.dc_intens,
                                            a.bsyn_early), indent=2)+'\n')
