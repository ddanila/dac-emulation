"""Explicit tightening of the XSPICE transient-error tolerance, independent of Newton tolerances."""
import re


def set_truncation_tolerance(deck, value):
    # This board's XSPICE A devices reduce the implicit default to 1.
    if not 0 < value <= 1:
        raise ValueError('Expected finite transient-error tolerance in (0, 1]')
    if re.search(r'\b(?:xtrtol|trtol)\b', deck, re.I) or deck.count('.control') != 1:
        raise ValueError('Ambiguous transient-error control')
    return deck.replace('.control', f'.options trtol={value:.17g}\n.control', 1)
