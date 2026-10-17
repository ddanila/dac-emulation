"""Check CPU-side reset delivery and restart in the BR service fixture."""
import re

from io_scenario import time_ns


class ResetMismatch(ValueError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


def validate_service_reset(log, scenario, first_byte):
    events = [(int(stamp), level) for stamp, level in re.findall(r'^RESET (\d+) ([01xz])$', log, re.M)]
    fetches = [(int(stamp), address, data) for stamp, address, data in re.findall(
        r'^FIRST_FETCH (\d+) ([0-9a-fx]+) ([0-9a-fx]+)$', log, re.M)]
    expected = [(time_ns(0) * 1000, '1')]
    expected += [(time_ns(event['cycle']) * 1000, '0' if event['asserted'] else '1') for event in scenario['resets']]
    evidence = {'signal': 'RESET_N', 'events': events, 'expectedTransitions': expected,
                'firstFetches': fetches, 'transitionToleranceNs': 3,
                'timingScope': 'SPICE fixture ramp/ADC and HDL timestamp rounding; not board reset propagation calibration'}
    def fail(message):
        raise ResetMismatch(message, evidence)
    if not events or any(level not in ('0', '1') for _, level in events):
        fail('Service RESET_N is missing or unknown')
    if any(b[0] < a[0] for a, b in zip(events, events[1:])):
        fail('Service RESET_N timestamps reverse')
    transitions = []
    for event in events:
        if not transitions or event[1] != transitions[-1][1]:
            transitions.append(event)
    if transitions[0][1] != '0' or transitions[0][0] >= expected[0][0]:
        fail('Service RESET_N did not assert before initial release')
    if len(transitions) - 1 != len(expected):
        fail('Service RESET_N transition count differs from fixture')
    for (stamp, level), (start, target) in zip(transitions[1:], expected):
        if level != target or not 0 <= stamp - start <= 3000:
            fail(f'Service RESET_N differs at fixture time {start} ps')
    releases = [stamp for stamp, level in transitions if level == '1']
    if len(fetches) != len(releases):
        evidence['signal'] = 'CPU first fetch'
        fail('CPU did not produce exactly one first-fetch observation per reset release')
    for index, (release, fetch) in enumerate(zip(releases, fetches)):
        stamp, address, data = fetch
        next_assertion = next((time for time, level in transitions if time > release and level == '0'), time_ns(scenario['cycles']) * 1000)
        if not release <= stamp < next_assertion or address != '0000' or data != f'{first_byte:02x}':
            evidence['signal'] = 'CPU first fetch'
            fail(f'CPU failed to restart at the first ROM byte after release {index}')
    return evidence
