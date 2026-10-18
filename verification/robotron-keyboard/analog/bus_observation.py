"""Check voltage agreement at TV80 input-register reads; not U880 pin timing."""
import math
import re
import json
from pathlib import Path
from collections import deque

from trace_io import open_text


class BusMismatch(ValueError):
    """First read-ordered mismatch with enough context to find its waveform."""
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


def measure(log, trace, step_ns, rom=None, setup_ns=0, hold_ns=0):
    limits = json.loads(Path(__file__).with_name('cpu_clock_limits.json').read_text())
    operating, inputs = limits['operatingConditions'], limits['ordinaryInput']
    if not all(math.isfinite(v) and v >= 0 for v in (step_ns, setup_ns, hold_ns)) or step_ns == 0:
        raise ValueError('Invalid bus observation interval')
    if rom is not None and len(rom) != 2048:
        raise ValueError('Expected mapped 2048-byte ROM')
    samples, latches = [], []
    for line in log.splitlines():
        if line.startswith('BUS_SAMPLE '):
            match = re.fullmatch(r'BUS_SAMPLE (\d+) ([0-9a-f]{4}) ([0-9a-f]{2}) ([01]) ([01]) ([01])', line)
            if not match:
                raise ValueError('Unknown or malformed sampled bus value: ' + line)
            time, address, value, memory, io, m1 = match.groups()
            sample = (int(time), int(address, 16), int(value, 16), int(memory), int(io), int(m1))
            if sample[3:5] not in ((0, 1), (1, 0)):
                raise ValueError('Ambiguous bus read selects')
            if samples and sample[0] <= samples[-1][0]:
                raise ValueError('Nonmonotonic bus read times')
            samples.append(sample)
        elif line.startswith('BUS_LATCH '):
            match = re.fullmatch(r'BUS_LATCH (\d+) ([0-9a-f]{2}) ([0-9a-f]{2})', line)
            if not match:
                raise ValueError('Unknown or malformed CPU latch value')
            time, expected, actual = match.groups()
            latches.append((int(time), int(expected, 16), int(actual, 16)))
    if not samples or len(samples) != len(latches):
        raise ValueError('Missing bus samples or CPU latch confirmations')
    for index, (sample, latch) in enumerate(zip(samples, latches)):
        if (not sample[0] < latch[0] or
            (index + 1 < len(samples) and latch[0] >= samples[index + 1][0])):
            raise ValueError('Invalid CPU latch ordering')

    def rows(stream):
        header = next(stream, '').lower().split()
        if header != ['time', *[f'v(n_d{i})' for i in range(8)], 'v(n_p5v)']:
            raise ValueError('Unexpected bus trace columns')
        last = None
        for line in stream:
            row = list(map(float, line.split()))
            if len(row) != 10 or not all(map(math.isfinite, row)) or (last is not None and row[0] < last):
                raise ValueError('Invalid bus trace row or time order')
            last = row[0]
            yield row

    low_margin, high_margin = math.inf, math.inf
    with open_text(trace) as stream:
        iterator = iter(rows(stream))
        current, history = next(iterator, None), deque()
        for ordinal, (time_ps, address, value, memory, _, _) in enumerate(samples):
            context = {'ordinal': ordinal, 'readTimePs': time_ps, 'address': address,
                       'sampledByte': value}
            if rom is not None and memory == 0 and value != rom[address & 2047]:
                raise BusMismatch('Sampled memory data differs from mapped ROM',
                                  dict(context, signal='ROM_DATA', expectedByte=rom[address & 2047]))
            latch = latches[ordinal]
            if latch[1:] != (value, value):
                raise BusMismatch('CPU input register differs from sampled bus',
                                  dict(context, signal='CPU_DI_REG', latchTimePs=latch[0],
                                       recordedSampleByte=latch[1], latchedByte=latch[2]))
            start = time_ps * 1e-12 - setup_ns * 1e-9
            end = time_ps * 1e-12 + hold_ns * 1e-9
            # Retain shared samples when requested setup/hold windows overlap.
            # Keep only one predecessor before the current window so long
            # pre-reset traces do not accumulate in memory.
            while len(history) > 1 and history[1][0] < start:
                history.popleft()
            while current is not None and current[0] <= end:
                history.append(current)
                while len(history) > 1 and history[1][0] < start:
                    history.popleft()
                current = next(iterator, None)
            window = list(history)
            if not window or window[-1][0] < end:
                if current is not None:
                    window.append(current)
            if not window or window[0][0] > start or window[-1][0] < end:
                raise ValueError('Bus trace does not bracket read window')
            if any(b[0] - a[0] > step_ns * 1.01e-9 + 1e-12 for a, b in zip(window, window[1:])):
                raise ValueError('Bus read window contains a waveform gap')
            for row in window:
                supply = row[-1]
                if not operating['supplyMinimumVolts'] <= supply <= operating['supplyMaximumVolts']:
                    raise BusMismatch('CPU bus read outside reference supply range',
                                      dict(context, signal='VCC', traceTimeSeconds=row[0], volts=supply,
                                           minimumVolts=operating['supplyMinimumVolts'],
                                           maximumVolts=operating['supplyMaximumVolts']))
                for bit, volts in enumerate(row[1:9]):
                    if not inputs['minimumVolts'] <= volts <= supply + inputs['maximumSupplyOffsetVolts']:
                        raise BusMismatch(f'Bus D{bit} outside reference input voltage range',
                                          dict(context, signal=f'D{bit}', traceTimeSeconds=row[0], volts=volts,
                                               minimumVolts=inputs['minimumVolts'],
                                               maximumVolts=supply + inputs['maximumSupplyOffsetVolts']))
                    high = bool(value & (1 << bit))
                    margin = volts - inputs['highMinimumVolts'] if high else inputs['lowMaximumVolts'] - volts
                    if margin < 0:
                        raise BusMismatch(f'Bus voltage disagrees with sampled D{bit} at {time_ps} ps',
                                          dict(context, signal=f'D{bit}', traceTimeSeconds=row[0], volts=volts,
                                               expectedBit=int(high), thresholdVolts=inputs['highMinimumVolts']
                                               if high else inputs['lowMaximumVolts']))
                    if high:
                        high_margin = min(high_margin, margin)
                    else:
                        low_margin = min(low_margin, margin)
        # Validate the tail too; malformed trailing samples must not be hidden.
        for _ in iterator:
            pass
    return {'passed': True, 'qualified': False, 'sampleCount': len(samples),
            'memoryReads': sum(sample[3] == 0 for sample in samples),
            'ioReads': sum(sample[4] == 0 for sample in samples),
            'firstReadPs': samples[0][0], 'lastReadPs': samples[-1][0],
            'minimumLowMarginVolts': None if math.isinf(low_margin) else low_margin,
            'minimumHighMarginVolts': None if math.isinf(high_margin) else high_margin,
            'setupNs': setup_ns, 'holdNs': hold_ns,
            'boundary': 'Sampled-voltage agreement and TV80 input-register confirmation only. '
                        'Windows include bracketing trace samples. No between-sample excursion proof, '
                        'U880 M1/M2-M5 edge-phase qualification or calibrated setup/hold timing.'}
