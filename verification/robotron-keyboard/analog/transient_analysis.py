"""Retain explicit breakpoint settings when ngspice invokes a deck analysis."""
import math
import re


def with_minimum_breakpoint(deck, femtoseconds):
    if femtoseconds is None:
        return deck
    if not math.isfinite(femtoseconds) or femtoseconds <= 0:
        raise ValueError('Minimum breakpoint spacing must be positive and finite')
    controls = re.findall(r'^\.control\n(.*?)^\.endc$', deck, re.M | re.S)
    if len(controls) != 1:
        raise ValueError('Expected one control block')
    commands = re.findall(r'^tran .+$', controls[0], re.M)
    if (len(commands) != 1 or len(re.findall(r'^tran .+$', deck, re.M)) != 1
            or re.search(r'^\.tran\b|^\.options\b.*\bminbreak\s*=|^run\s*$', deck, re.M | re.I)):
        raise ValueError('Conflicting transient analysis or breakpoint setting')
    # ngspice 47's control tran task does not copy TSKminBreak. Deck tran/run does.
    command = commands[0]
    deck = deck.replace('.control\n', f'.options minbreak={femtoseconds:.17g}f\n.{command}\n.control\n')
    return re.sub(r'^' + re.escape(command) + '$', 'run', deck, flags=re.M)
