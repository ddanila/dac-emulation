"""Check settled WR voltage and explicit output ownership in retained traces."""
import math
import re

from trace_io import open_text


def measure(log, trace, step_ns, end_seconds, start_seconds=.001, settling_ns=500):
    if (not all(math.isfinite(value) for value in (step_ns, end_seconds, start_seconds, settling_ns))
            or step_ns <= 0 or not 0 <= start_seconds < end_seconds or settling_ns < 0):
        raise ValueError('Invalid WR observation interval')
    events = []
    for line in log.splitlines():
        match = re.fullmatch(r'WR_DRIVE (\d+) ([01xz]{2})', line)
        if not match:
            if line.startswith('WR_DRIVE '):
                raise ValueError('Malformed WR ownership event')
            continue
        time, state = int(match[1]) * 1e-12, match[2]
        if events and time < events[-1][0]:
            raise ValueError('WR ownership events run backwards')
        # HDL delta cycles at one instant have no elapsed analog duration.
        if events and time == events[-1][0]:
            events[-1] = (time, state)
        else:
            events.append((time, state))
    if not events or events[0][0] > start_seconds:
        raise ValueError('Missing initial WR ownership')
    index, previous, first, last, count = 0, None, None, None, 0
    checked = {'01': 0, '10': 0, '00': 0}
    checked_intervals = set()
    with open_text(trace) as stream:
        header = next(stream, '').lower().split()
        if header != ['time', 'v(n_wr_n)', 'v(wr_low)', 'v(wr_high)', '@bwr_low[i]', '@bwr_high[i]', 'v(n_p5v)']:
            raise ValueError('Unexpected WR trace columns')
        for line in stream:
            row = list(map(float, line.split()))
            if len(row) != 7 or not all(map(math.isfinite, row)):
                raise ValueError('Invalid WR waveform row')
            time, volts, low, high, ilow, ihigh, supply = row
            if time < 0:
                raise ValueError('Negative WR waveform time')
            if previous is not None and (time < previous or time - previous > step_ns * 1.01e-9 + 1e-12):
                raise ValueError('WR waveform gap or backwards time')
            first = time if first is None else first
            previous = last = time
            count += 1
            while index + 1 < len(events) and events[index + 1][0] <= time:
                index += 1
            changed, state = events[index]
            if time < start_seconds or time < changed + settling_ns * 1e-9:
                continue
            if state not in checked:
                raise ValueError(f'Unknown WR ownership persists at {time:.17g} s')
            if not 4.75 <= supply <= 5.25 or not -.5 <= volts <= supply:
                raise ValueError(f'WR supply or pin voltage out of reference range at {time:.17g} s')
            if abs(low - 5 * int(state[0])) > 1e-6 or abs(high - 5 * int(state[1])) > 1e-6:
                raise ValueError(f'WR DAC ownership differs from HDL at {time:.17g} s')
            if (state == '10' and volts > .8) or (state == '01' and volts < 2):
                raise ValueError(f'WR settled voltage differs from drive at {time:.17g} s')
            if (state[0] == '0' and abs(ilow) > 1e-12) or (state[1] == '0' and abs(ihigh) > 1e-12):
                raise ValueError(f'Released WR driver still sources current at {time:.17g} s')
            checked[state] += 1
            checked_intervals.add(index)
    if not count or first > 1e-9 or abs(last - end_seconds) > 1e-12:
        raise ValueError('Incomplete WR waveform extent')
    if not checked['10'] or not checked['01']:
        raise ValueError('WR firmware assertion and deassertion not both observed')
    unobserved = [i for i, (time, state) in enumerate(events)
                  if start_seconds <= time < end_seconds and state in ('10', '01')
                  and i not in checked_intervals]
    if unobserved:
        raise ValueError('WR transitions lack settled observations: ' + repr(unobserved[:8]))
    return {'passed': True, 'qualified': False, 'settlingNs': settling_ns,
            'checkedSamples': checked, 'checkedIntervals': len(checked_intervals),
            'firstSeconds': first, 'lastSeconds': last, 'rows': count,
            'boundary': 'Settled voltage and drive ownership checks only; no U880 edge timing, '
                        'between-sample excursion or transistor switching calibration. '
                        'Bus handover is covered only if release samples are nonzero.'}
