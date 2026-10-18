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


def measure(log, trace, step_ns, rom=None, setup_ns=0, hold_ns=0, trace_extent=None, start_tolerance_ns=0):
    limits = json.loads(Path(__file__).with_name('cpu_clock_limits.json').read_text())
    operating, inputs = limits['operatingConditions'], limits['ordinaryInput']
    if not all(math.isfinite(v) and v >= 0 for v in (step_ns, setup_ns, hold_ns)) or step_ns == 0:
        raise ValueError('Invalid bus observation interval')
    if rom is not None and len(rom) != 2048:
        raise ValueError('Expected mapped 2048-byte ROM')
    if trace_extent is not None and (len(trace_extent) != 2 or
        not all(math.isfinite(t) and t >= 0 for t in trace_extent) or trace_extent[0] >= trace_extent[1]):
        raise ValueError('Invalid expected bus capture extent')
    if (not math.isfinite(start_tolerance_ns) or not 0 <= start_tolerance_ns <= step_ns
            or (start_tolerance_ns and trace_extent is None)):
        raise ValueError('Invalid bus capture start tolerance')
    samples, latches, drives = [], [], []
    for line in log.splitlines():
        if line.startswith('BUS_SAMPLE '):
            match = re.fullmatch(r'BUS_SAMPLE (\d+) ([0-9a-fA-F]{4}) ([0-9a-fA-FxXzZ]{2}) ([01]) ([01]) ([01])', line)
            if not match:
                raise ValueError('Unknown or malformed sampled bus value: ' + line)
            time, address, value, memory, io, m1 = match.groups()
            sample = (int(time), int(address, 16), value, int(memory), int(io), int(m1))
            if sample[3:5] not in ((0, 1), (1, 0)):
                raise ValueError('Ambiguous bus read selects')
            if samples and sample[0] <= samples[-1][0]:
                raise ValueError('Nonmonotonic bus read times')
            samples.append(sample)
        elif line.startswith('BUS_DRIVE '):
            match = re.fullmatch(r'BUS_DRIVE (\d+) ([01xXzZ]{24}) ([01xXzZ]{24})', line)
            if not match:
                raise ValueError('Malformed bus driver observation')
            time, low, high = match.groups()
            drives.append((int(time), low.lower(), high.lower()))
        elif line.startswith('BUS_LATCH '):
            match = re.fullmatch(r'BUS_LATCH (\d+) ([0-9a-fA-FxXzZ]{2}) ([0-9a-fA-FxXzZ]{2})', line)
            if not match:
                raise ValueError('Unknown or malformed CPU latch value')
            time, expected, actual = match.groups()
            latches.append((int(time), expected, actual))
    if not samples or len(samples) != len(latches):
        raise ValueError('Missing bus samples or CPU latch confirmations')
    if drives and (len(drives) != len(samples) or
                   any(drive[0] != sample[0] for drive, sample in zip(drives, samples))):
        raise ValueError('Missing or misaligned bus driver observations')
    for index, (sample, latch) in enumerate(zip(samples, latches)):
        if (sample[0] > latch[0] or
            (index + 1 < len(samples) and latch[0] >= samples[index + 1][0])):
            raise ValueError('Invalid CPU latch ordering')

    extent = {'firstSeconds': None, 'lastSeconds': None, 'rows': 0}

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
            if extent['firstSeconds'] is None:
                extent['firstSeconds'] = row[0]
            extent['lastSeconds'] = row[0]
            extent['rows'] += 1
            yield row

    low_margin, high_margin = math.inf, math.inf
    with open_text(trace) as stream:
        iterator = iter(rows(stream))
        current, history = next(iterator, None), deque()
        for ordinal, (time_ps, address, raw_value, memory, io, m1) in enumerate(samples):
            latch = latches[ordinal]
            uncertain = any(c in 'xXzZ' for raw in (raw_value, *latch[1:]) for c in raw)
            value = None if any(c in 'xXzZ' for c in raw_value) else int(raw_value, 16)
            context = {'ordinal': ordinal, 'readTimePs': time_ps, 'address': address,
                       'sampledByte': value}
            if drives:
                _, low, high = drives[ordinal]
                context['drivers'] = {
                    name: {'lowEnableBits7To0': low[16-8*i:24-8*i],
                           'highEnableBits7To0': high[16-8*i:24-8*i]}
                    for i, name in enumerate(('cpu', 'rom', 'latch'))}
            # Data uncertainty is a read failure, not a log syntax error. Defer
            # it until this read so it cannot hide an earlier voltage failure.
            if uncertain:
                raise BusMismatch('Unknown sampled bus or CPU latch data',
                                  dict(context, signal='CPU_DI_UNKNOWN', sampledHex=raw_value,
                                       recordedSampleHex=latch[1], latchedHex=latch[2],
                                       latchTimePs=latch[0], memorySelectN=memory,
                                       ioSelectN=io, m1N=m1))
            latch = (latch[0], int(latch[1], 16), int(latch[2], 16))
            if rom is not None and memory == 0 and value != rom[address & 2047]:
                raise BusMismatch('Sampled memory data differs from mapped ROM',
                                  dict(context, signal='ROM_DATA', expectedByte=rom[address & 2047]))
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
    if trace_extent is not None and (extent['firstSeconds'] is None or
        extent['firstSeconds'] < trace_extent[0] - 1e-12 or
        extent['firstSeconds'] > trace_extent[0] + start_tolerance_ns * 1e-9 + 1e-12 or
        abs(extent['lastSeconds'] - trace_extent[1]) > 1e-12):
        raise ValueError('Incomplete bus waveform capture extent')
    if start_tolerance_ns:
        extent['requestedStartSeconds'] = trace_extent[0]
        extent['startToleranceNs'] = start_tolerance_ns
        extent['startOffsetSeconds'] = extent['firstSeconds'] - trace_extent[0]
    return {'passed': True, 'qualified': False, 'sampleCount': len(samples), 'driverStatesCaptured': bool(drives),
            'waveform': extent,
            'memoryReads': sum(sample[3] == 0 for sample in samples),
            'ioReads': sum(sample[4] == 0 for sample in samples),
            'firstReadPs': samples[0][0], 'lastReadPs': samples[-1][0],
            'minimumLowMarginVolts': None if math.isinf(low_margin) else low_margin,
            'minimumHighMarginVolts': None if math.isinf(high_margin) else high_margin,
            'setupNs': setup_ns, 'holdNs': hold_ns,
            'boundary': 'Sampled-voltage agreement and TV80 input-register confirmation only. '
                        'Windows include bracketing trace samples. No between-sample excursion proof, '
                        'U880 M1/M2-M5 edge-phase qualification or calibrated setup/hold timing.'}
