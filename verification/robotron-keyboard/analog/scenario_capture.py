"""Keep a full-scenario capture tied to its declared stimulus endpoint."""
from decimal import Decimal, InvalidOperation
import re
from io_scenario import time_ns


def endpoint_ns(deck, scenario, requested=None):
    expected = time_ns(scenario['cycles'])
    transients = re.findall(r'^\s*\.tran\s+([^\r\n]+)$', deck, re.M | re.I)
    if len(transients) != 1:
        raise ValueError('Expected one scenario transient')
    fields = transients[0].split()
    if len(fields) != 2 or not fields[1].lower().endswith('n'):
        raise ValueError('Expected a complete scenario transient in nanoseconds')
    try:
        declared = Decimal(fields[1][:-1])
        override = Decimal(str(requested)) if requested is not None else Decimal(expected)
    except InvalidOperation as exc:
        raise ValueError('Invalid scenario endpoint') from exc
    if not declared.is_finite() or not override.is_finite() or declared != expected or override != expected:
        raise ValueError('Capture endpoint differs from complete scenario')
    if re.search(r'^\s*(?:stop|resume)\b', deck, re.M | re.I):
        raise ValueError('Full scenario cannot contain a diagnostic halt')
    return expected
