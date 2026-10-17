"""One cycle-indexed stimulus source for electrical fixtures and the C reference."""
import json


def load(path):
    scenario = json.loads(path.read_text())
    if not isinstance(scenario, dict) or set(scenario) != {'name', 'cycles', 'contacts', 'resets', 'observations'}:
        raise ValueError('Expected scenario name, cycles, contacts, resets and observations')
    if not isinstance(scenario['name'], str) or not scenario['name'].strip():
        raise ValueError('Scenario needs a name')
    duration = scenario['cycles']
    if type(duration) is not int or not 1 <= duration <= 10000000:
        raise ValueError('Scenario cycles must be an integer in [1, 10000000]')
    for kind, keys in [('contacts', {'cycle', 'index', 'closed'}), ('resets', {'cycle', 'asserted'})]:
        events = scenario[kind]
        if not isinstance(events, list):
            raise ValueError('Expected event list: ' + kind)
        previous, seen, states = -1, set(), {}
        for event in events:
            if not isinstance(event, dict) or set(event) != keys:
                raise ValueError('Unexpected event fields: ' + kind)
            cycle = event['cycle']
            if type(cycle) is not int or not (0 if kind == 'contacts' else 1) <= cycle < duration or cycle < previous:
                raise ValueError('Events must be ordered integer cycles within the scenario')
            index = event.get('index', 0)
            if type(index) is not int or not 0 <= index < 104:
                raise ValueError('Contact index outside the matrix')
            state = event['closed' if kind == 'contacts' else 'asserted']
            if type(state) is not bool or (cycle, index) in seen or state == states.get(index, False):
                raise ValueError('Duplicate, non-boolean or ineffective state change')
            seen.add((cycle, index))
            states[index] = state
            previous = cycle
    if not isinstance(scenario['observations'], list) or not scenario['observations']:
        raise ValueError('Scenario needs observable acceptance windows')
    names = set()
    for window in scenario['observations']:
        required = {'name', 'startCycle', 'endCycle', 'minimumBits'}
        if not isinstance(window, dict) or not required <= set(window) or set(window) - required - {'maximumBits', 'differentFrom'}:
            raise ValueError('Unexpected observation fields')
        name = window['name']
        if not isinstance(name, str) or not name or name in names:
            raise ValueError('Observation names must be nonempty and unique')
        if any(type(window[key]) is not int for key in ('startCycle', 'endCycle', 'minimumBits')):
            raise ValueError('Observation bounds must be integers')
        if not 0 <= window['startCycle'] < window['endCycle'] <= duration or window['minimumBits'] < 0:
            raise ValueError('Invalid observation window or bit minimum')
        if 'maximumBits' in window and (type(window['maximumBits']) is not int or window['maximumBits'] < window['minimumBits']):
            raise ValueError('Invalid observation bit maximum')
        if 'differentFrom' in window and (not isinstance(window['differentFrom'], str) or window['differentFrom'] not in names):
            raise ValueError('Observation comparison must name an earlier window')
        names.add(name)
    return scenario


def observe(scenario, events, electrical=False):
    # Electrical observations are absolute picoseconds; C observations are cycles
    # after initial reset release. Neither comparison claims CPU cycle equivalence.
    observations = [((stamp * 1e-3 - 1000000) / 1000 if electrical else stamp, bit)
                    for stamp, bit in events]
    windows, sequences = [], {}
    for window in scenario['observations']:
        bits = [bit for cycle, bit in observations if window['startCycle'] <= cycle < window['endCycle']]
        passed = len(bits) >= window['minimumBits'] and len(bits) <= window.get('maximumBits', float('inf'))
        if 'differentFrom' in window:
            passed &= bits != sequences[window['differentFrom']]
        sequences[window['name']] = bits
        windows.append({**window, 'observedBits': bits, 'passed': passed})
    return {'passed': all(window['passed'] for window in windows), 'windows': windows}


def time_ns(cycle):
    # External reset releases at 1 ms; the fixture clock period is 1 us.
    return 1000000 + cycle * 1000


def contact_source(scenario, index):
    events = [event for event in scenario['contacts'] if event['index'] == index]
    if not events:
        return '0'
    points, level = ['0 0'], 0
    for event in events:
        time = time_ns(event['cycle'])
        points.append(f'{time}n {level}')
        level = 5 if event['closed'] else 0
        points.append(f'{time + 1}n {level}')
    return 'PWL(' + ' '.join(points) + ')'


def reset_source(scenario):
    points, level = ['0 0', '1000000n 0', '1000001n 5'], 5
    for event in scenario['resets']:
        time = time_ns(event['cycle'])
        points.append(f'{time}n {level}')
        level = 0 if event['asserted'] else 5
        points.append(f'{time + 1}n {level}')
    return 'PWL(' + ' '.join(points) + ')'


def c_header(scenario):
    contacts = [f'{{{e["cycle"]}, {e["index"]}, {int(e["closed"])}}}' for e in scenario['contacts']]
    resets = [f'{{{e["cycle"]}, {int(e["asserted"])}}}' for e in scenario['resets']]
    return '\n'.join([
        '#include <limits.h>', f'#define SCENARIO_CYCLES {scenario["cycles"]}u',
        'static const struct { unsigned cycle, index, closed; } contact_events[] = {',
        ',\n'.join(contacts + ['{UINT_MAX, 0, 0}']), '};',
        'static const struct { unsigned cycle, asserted; } reset_events[] = {',
        ',\n'.join(resets + ['{UINT_MAX, 0}']), '};', ''])
