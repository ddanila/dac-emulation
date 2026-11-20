"""Measure the page-18 contrast control in the loaded input/neck stage."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import electrothermal
import signal_path
import steady_supply

ROOT = Path(__file__).resolve().parent
POSITIONS = (.05, .5, .95)
PROBE = 'cathode'


def samples(path, vector):
    with Path(path).open() as stream:
        columns = next(stream).split()
        if columns[0] != 'time' or vector not in columns:
            raise ValueError(vector+' waveform absent from stage trace')
        index = columns.index(vector)
        return [(float(row[0]), float(row[index])) for line in stream
                if (row := line.split())]


def warm_tube(deck, folder, thermal_rise):
    """Replace the fixed beam load with the repository's held-warm CRT proxy."""
    replacements = (
        ('Ibeam mreturn cathode 20u',
         'Vp10_7 p10_7 mreturn 10.7\nVanode anode mreturn 11500\n'
         'Xcrt p10_7 mreturn cathode ug1 ug2 anode heater_rise cathode_rise CRT_THERMAL'),
        ('Csocket cathode mreturn {tube_cathode_c}', ''),
        ('.options reltol=', electrothermal.model(initial_rise_k=thermal_rise,
                                                  hold_temperature=True)+'\n.options reltol='),
        ('linearize computer_video',
         'let beam_ua = v(xcrt.launch_current_ua)\nlinearize beam_ua computer_video'),
        ('wrdata samples.txt computer_video', 'wrdata samples.txt beam_ua computer_video'),
    )
    for old, new in replacements:
        if deck.count(old) != 1:
            raise ValueError('loaded input/neck deck contract changed: '+old)
        deck = deck.replace(old, new)
    folder.mkdir()
    (folder/'run.cir').write_text(deck)
    process = subprocess.run(['ngspice', '-b', 'run.cir'], cwd=folder,
                             capture_output=True, text=True)
    log = process.stdout+process.stderr
    if process.returncode or 'Error:' in log or 'Timestep too small' in log or not (folder/'samples.txt').is_file():
        raise RuntimeError('held-warm contrast-stage solve failed: '+log[-400:])
    return samples(folder/'samples.txt', 'beam_ua')


def run(capture_path):
    capture_path = Path(capture_path)
    capture = json.loads(capture_path.read_text())
    if capture.get('format') != 'dac-monitor-input-v2':
        raise ValueError('contrast check needs a v2 three-channel capture')
    window = [row for row in capture['events']
              if row[0] <= .0002*capture['clock_hz']]
    if len(window) < 2 or any(not any(a[channel] != b[channel]
                                      for a, b in zip(window, window[1:]))
                              for channel in (1, 3)):
        raise ValueError('contrast check needs video and intensity transitions')
    with tempfile.TemporaryDirectory() as directory:
        rows = []
        traces = []
        beam_traces = []
        thermal = steady_supply.heater_equilibrium()
        for position in POSITIONS:
            folder = Path(directory)/f'contrast-{position:g}'
            result = signal_path.run(capture_path, folder, duration=.0002,
                                     step=5e-9, changes={'contrast_position': position})
            if result['status'] != 'complete':
                raise ValueError('loaded contrast-stage solve did not complete')
            deck = (folder/'run.cir').read_text()
            if any(item not in deck for item in
                   ('Vp35 p35 mreturn 35', 'Rbrightness_top p35 collector_i',
                    'Rbrightness_bottom collector_i contrast_adjust',
                    'Rcontrast reference9 contrast_low')):
                raise ValueError('contrast stage lacks the source-addressed controls or feed')
            waveform = samples(folder/'samples.txt', PROBE)
            traces.append(waveform)
            beam = warm_tube(deck, Path(directory)/f'warm-{position:g}',
                             thermal['temperature_rise_k'])
            beam_traces.append(beam)
            beam_values = [value for _, value in beam]
            rows.append({'contrast_position': position,
                         'contrast_resistance_ohm': result['parameters']['contrast_r']*position,
                         'cathode': result['metrics'][PROBE],
                         'receiver_video': result['metrics']['receiver_video'],
                         'receiver_intens': result['metrics']['receiver_intens'],
                         'conditional_held_warm_beam_ua': {
                             'minimum': min(beam_values), 'maximum': max(beam_values),
                             'mean': sum((a[1]+b[1])*.5*(b[0]-a[0])
                                         for a,b in zip(beam,beam[1:]))/(beam[-1][0]-beam[0][0])},
                         'deck_sha256': result['hashes']['deck']})
    times = [time for time, _ in traces[0]]
    if not times or any([time for time, _ in trace] != times for trace in traces[1:]):
        raise ValueError('contrast waveform time grids differ')
    low, high = traces[0], traces[-1]
    maximum_difference = max(abs(a[1]-b[1]) for a, b in zip(low, high))
    cathode_swing = rows[1]['cathode']['peak_to_peak']
    if any([time for time,_ in beam] != times for beam in beam_traces):
        raise ValueError('held-warm beam time grids differ from fixed-load stage')
    beam_difference = max(abs(a[1]-b[1]) for a,b in zip(beam_traces[0],beam_traces[-1]))
    beam_scale = rows[1]['conditional_held_warm_beam_ua']['maximum']
    return {'format': 'dac-monitor-page18-contrast-stage-check-v2',
            'qualification': 'source-addressed input/neck stage with ideal 5/12/35/41 V rails and bounded synthetic highlight stimulus; fixed-beam and provisional held-warm CRT responses, not a complete page-3/4 netlist, calibrated contrast, native grid or sustained monitor score',
            'input_sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'input_qualification': capture.get('qualification'),
            'signal_path_sha256': hashlib.sha256((ROOT/'signal_path.py').read_bytes()).hexdigest(),
            'electrothermal_sha256': hashlib.sha256((ROOT/'electrothermal.py').read_bytes()).hexdigest(),
            'steady_supply_sha256': hashlib.sha256((ROOT/'steady_supply.py').read_bytes()).hexdigest(),
            'stimulus': {'duration_s': .0002, 'step_s': 5e-9,
                         'reason': 'highlight pattern toggles both video and intensity in the retained window'},
            'held_warm_tube': {'thermal_rise_k': thermal['temperature_rise_k'],
                               'heater_power_w': thermal['heater_power_w'],
                               'anode_v': 11500, 'g1_v': -25, 'g2_v': 350,
                               'qualification': 'provisional class-typical emission model and fixed ideal electrode supplies'},
            'rows': rows, 'sample_count': len(times),
            'low_high_cathode_max_absolute_difference_v': maximum_difference,
            'low_high_cathode_relative_to_mid_swing': maximum_difference/max(cathode_swing, 1e-12),
            'low_high_beam_max_absolute_difference_ua': beam_difference,
            'low_high_beam_relative_to_mid_peak': beam_difference/max(beam_scale,1e-12),
            'functional_result': 'provisional tube response only; page-18 contrast function and service-meter targets remain unqualified',
            'remaining': ['Re-read page-3/4 R4/V1/V3/intensity connectivity against the independent source netlist',
                          'Qualify the tube emission and 35 V feed, then run the full-bright service-meter and native-grid procedure']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.capture)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('contrast low/high cathode and provisional beam differences:',
          f"{report['low_high_cathode_max_absolute_difference_v']:.6g} V, "
          f"{report['low_high_beam_max_absolute_difference_ua']:.6g} uA")


if __name__ == '__main__':
    main()
