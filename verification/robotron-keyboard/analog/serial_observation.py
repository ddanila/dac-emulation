"""Compare firmware serial intent with the independently thresholded cable receiver."""
import re


def validate_transport(log, require_activity=False):
    observations = {}
    for kind in ('TX', 'RX'):
        events = []
        for record in re.findall(r'^SERIAL_' + kind + r' (.*)$', log, re.M):
            match = re.fullmatch(r'(\d+) ([01])', record)
            if not match:
                raise ValueError('Unknown or malformed serial ' + kind + ' observation: ' + record)
            stamp, bit = int(match[1]), int(match[2])
            if events and stamp <= events[-1][0]:
                raise ValueError('Non-increasing serial ' + kind + ' timestamps')
            events.append((stamp, bit))
        observations[kind] = events
    tx, rx = observations['TX'], observations['RX']
    if require_activity and not tx:
        raise ValueError('Firmware scenario produced no serial activity')
    if len(tx) != len(rx):
        raise ValueError('Transmitted and received serial edge counts differ')
    delays = []
    for i, ((sent_at, sent), (received_at, received)) in enumerate(zip(tx, rx)):
        if sent != received:
            raise ValueError('Cable receiver changed serial bit at index ' + str(i))
        if received_at <= sent_at or (i + 1 < len(tx) and received_at >= tx[i + 1][0]):
            raise ValueError('Receiver edge is not causally paired with transmitted edge')
        delays.append((received_at - sent_at) * 1e-12)
    return {'activityObserved': bool(tx), 'transmitted': tx, 'received': rx,
            'clockTransportSeconds': delays,
            'scope': 'Bit transport only; no S600 frame or key-semantics claim from matching intent'}
