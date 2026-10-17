"""Compare firmware serial intent with the independently thresholded cable receiver."""
import re


class SerialMismatch(ValueError):
    def __init__(self, message, details):
        super().__init__(message)
        self.details = details


def first_reference_difference(reference, received):
    """Ordinal bit comparison; preserve both clocks without implying alignment."""
    for index in range(max(len(reference), len(received))):
        expected = reference[index] if index < len(reference) else None
        observed = received[index] if index < len(received) else None
        if expected is None or observed is None or expected[1] != observed[1]:
            return {'signal': 'serial_data', 'ordinal': index,
                    'expected': {'cycle': expected[0], 'bit': expected[1]} if expected else None,
                    'observed': {'timePs': observed[0], 'bit': observed[1]} if observed else None,
                    'comparison': 'Ordinal bits; C cycles and receiver time are not clock-aligned'}
    return None


def validate_transport(log, require_activity=False):
    observations = {}
    for kind in ('TX', 'RX'):
        events = []
        for record in re.findall(r'^SERIAL_' + kind + r' (.*)$', log, re.M):
            match = re.fullmatch(r'(\d+) ([01])', record)
            if not match:
                raise SerialMismatch('Unknown or malformed serial ' + kind + ' observation: ' + record,
                                     {'signal': 'serial_' + kind, 'ordinal': len(events), 'record': record})
            stamp, bit = int(match[1]), int(match[2])
            if events and stamp <= events[-1][0]:
                raise SerialMismatch('Non-increasing serial ' + kind + ' timestamps',
                                     {'signal': 'serial_clock_' + kind, 'ordinal': len(events),
                                      'previousTimePs': events[-1][0], 'timePs': stamp})
            events.append((stamp, bit))
        observations[kind] = events
    tx, rx = observations['TX'], observations['RX']
    if require_activity and not tx:
        raise SerialMismatch('Firmware scenario produced no serial activity', {'signal': 'serial_clock_TX', 'activityObserved': False})
    if len(tx) != len(rx):
        index = min(len(tx), len(rx))
        raise SerialMismatch('Transmitted and received serial edge counts differ',
                             {'signal': 'serial_clock', 'transmittedCount': len(tx), 'receivedCount': len(rx),
                              'firstUnpairedOrdinal': index,
                              'transmittedEvent': tx[index] if index < len(tx) else None,
                              'receivedEvent': rx[index] if index < len(rx) else None,
                              'interpretation': 'First unpaired ordinal, not proof of where an edge was lost'})
    delays = []
    for i, ((sent_at, sent), (received_at, received)) in enumerate(zip(tx, rx)):
        if sent != received:
            raise SerialMismatch('Cable receiver changed serial bit at index ' + str(i),
                                 {'signal': 'serial_data', 'ordinal': i, 'transmittedTimePs': sent_at,
                                  'receivedTimePs': received_at, 'expectedBit': sent, 'observedBit': received})
        if received_at <= sent_at or (i + 1 < len(tx) and received_at >= tx[i + 1][0]):
            raise SerialMismatch('Receiver edge is not causally paired with transmitted edge',
                                 {'signal': 'serial_clock', 'ordinal': i, 'transmittedTimePs': sent_at,
                                  'receivedTimePs': received_at,
                                  'nextTransmittedTimePs': tx[i + 1][0] if i + 1 < len(tx) else None})
        delays.append((received_at - sent_at) * 1e-12)
    return {'activityObserved': bool(tx), 'transmitted': tx, 'received': rx,
            'clockTransportSeconds': delays,
            'scope': 'Bit transport only; no S600 frame or key-semantics claim from matching intent'}
