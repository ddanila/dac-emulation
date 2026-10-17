"""Check nominal LED currents against settled firmware-driven intent voltages."""
import math


def measure(path, step_ns, require_activity=False, settling_ns=100, start_seconds=0):
    states = [None, None]
    since = [None, None]
    channels = [{'onSamples': 0, 'offSamples': 0, 'minimumOnAmps': None, 'maximumOffAmps': 0}
                for _ in range(2)]
    previous = None
    first = None
    count = 0
    failure = None
    with path.open() as stream:
        next(stream)
        for line in stream:
            row = [float(value) for value in line.split()]
            if len(row) != 5 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid LED waveform')
            time = row[0]
            if previous is not None and (time < previous or (time - previous) * 1e9 > step_ns + 1):
                raise ValueError('LED waveform reverses or exceeds the declared timestep')
            first = time if first is None else first
            previous = time
            count += 1
            for index, (intent, current) in enumerate(zip(row[1:3], row[3:5])):
                state = False if intent < .8 else True if intent > 4.2 else None
                if state != states[index]:
                    states[index], since[index] = state, time
                if since[index] is None:
                    since[index] = time
                if time < start_seconds or (time - since[index]) * 1e9 < settling_ns:
                    continue
                if state is None:
                    if failure is None:
                        failure = {'signal': ('SI/SO', 'Caps')[index] + ' LED intent',
                                   'timeSeconds': time, 'intentVolts': intent}
                    continue
                channel = channels[index]
                if state:
                    channel['onSamples'] += 1
                    channel['minimumOnAmps'] = current if channel['minimumOnAmps'] is None else min(channel['minimumOnAmps'], current)
                    valid = current > .001
                else:
                    channel['offSamples'] += 1
                    channel['maximumOffAmps'] = max(channel['maximumOffAmps'], abs(current))
                    valid = abs(current) < .0001
                if not valid and failure is None:
                    failure = {'signal': ('SI/SO', 'Caps')[index] + ' LED current',
                               'timeSeconds': time, 'intentVolts': intent, 'currentAmps': current}
    if not count or any(c['onSamples'] + c['offSamples'] == 0 for c in channels):
        raise ValueError('LED waveform has no settled observations')
    activity = all(c['onSamples'] and c['offSamples'] for c in channels)
    return {'passed': failure is None and (not require_activity or bool(activity)),
            'firstFailure': failure, 'bothIndicatorsExercised': bool(activity),
            'requireActivity': require_activity, 'channels': dict(zip(('siso', 'caps'), channels)),
            'firstSampleSeconds': first, 'lastSampleSeconds': previous, 'waveformRows': count,
            'settlingNs': settling_ns, 'checkStartSeconds': start_seconds, 'onMinimumAmps': .001, 'offMaximumAmps': .0001,
            'scope': 'Nominal load response to firmware-driven intents; not brightness, device calibration or C LED-state equivalence'}
