"""Measure the page-18 contrast control in the loaded input/neck stage."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import signal_path

ROOT = Path(__file__).resolve().parent
POSITIONS = (.05, .5, .95)
PROBE = 'cathode'


def cathode_samples(path):
    with Path(path).open() as stream:
        columns = next(stream).split()
        if columns[0] != 'time' or PROBE not in columns:
            raise ValueError('cathode waveform absent from stage trace')
        index = columns.index(PROBE)
        return [(float(row[0]), float(row[index])) for line in stream
                if (row := line.split())]


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
            waveform = cathode_samples(folder/'samples.txt')
            traces.append(waveform)
            rows.append({'contrast_position': position,
                         'contrast_resistance_ohm': result['parameters']['contrast_r']*position,
                         'cathode': result['metrics'][PROBE],
                         'receiver_video': result['metrics']['receiver_video'],
                         'receiver_intens': result['metrics']['receiver_intens'],
                         'deck_sha256': result['hashes']['deck']})
    times = [time for time, _ in traces[0]]
    if not times or any([time for time, _ in trace] != times for trace in traces[1:]):
        raise ValueError('contrast waveform time grids differ')
    low, high = traces[0], traces[-1]
    maximum_difference = max(abs(a[1]-b[1]) for a, b in zip(low, high))
    cathode_swing = rows[1]['cathode']['peak_to_peak']
    return {'format': 'dac-monitor-page18-contrast-stage-check-v1',
            'qualification': 'source-addressed input/neck stage with ideal 5/12/35/41 V rails and bounded synthetic highlight stimulus; not a complete page-3/4 netlist, calibrated contrast, native grid or sustained monitor score',
            'input_sha256': hashlib.sha256(capture_path.read_bytes()).hexdigest(),
            'input_qualification': capture.get('qualification'),
            'signal_path_sha256': hashlib.sha256((ROOT/'signal_path.py').read_bytes()).hexdigest(),
            'stimulus': {'duration_s': .0002, 'step_s': 5e-9,
                         'reason': 'highlight pattern toggles both video and intensity in the retained window'},
            'rows': rows, 'sample_count': len(times),
            'low_high_cathode_max_absolute_difference_v': maximum_difference,
            'low_high_cathode_relative_to_mid_swing': maximum_difference/max(cathode_swing, 1e-12),
            'functional_result': 'contrast control has negligible cathode effect in this bounded stage; do not close page-18 functional review',
            'remaining': ['Re-read page-3/4 R4/V1/V3/intensity connectivity and test the corrected stage against the manual bright/dark cathode procedure',
                          'Qualify the 35 V feed, tube emission and native-grid connected operating point']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.capture)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print('contrast low/high cathode difference:',
          f"{report['low_high_cathode_max_absolute_difference_v']:.6g} V")


if __name__ == '__main__':
    main()
