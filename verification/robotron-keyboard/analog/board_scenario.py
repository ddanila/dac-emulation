"""Apply contact recipes to a board running from its own electrical clock/reset."""
from io_scenario import load, observe

ORIGIN_NS = 125000000
TICK_NS = 1000


def load_board_scenario(path):
    scenario = load(path)
    if scenario['resets']:
        raise ValueError('Board contact scenarios cannot force CPU reset with BR2 closed; use the service fixture')
    return scenario


def contact_source(scenario, index):
    points, level = ['0 0'], 0
    for event in scenario['contacts']:
        if event['index'] != index:
            continue
        stamp = ORIGIN_NS + event['cycle'] * TICK_NS
        points.append(f'{stamp}n {level}')
        level = 5 if event['closed'] else 0
        points.append(f'{stamp + 1}n {level}')
    return 'PWL(' + ' '.join(points) + ')' if len(points) > 1 else '0'


def stop_seconds(scenario):
    return (ORIGIN_NS + scenario['cycles'] * TICK_NS) * 1e-9


def coverage(scenario, received):
    # The shared recipe's index is a wall-time tick here, not a board CPU cycle.
    events = [((stamp * 1e-3 - ORIGIN_NS) / TICK_NS, bit) for stamp, bit in received]
    return observe(scenario, events)
