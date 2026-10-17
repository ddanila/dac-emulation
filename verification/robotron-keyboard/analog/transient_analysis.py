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


def normalized_analysis(deck, assumptions, step_key="maximumStepNs"):
    steps = re.findall(r'^(\.?tran) ([0-9.eE+-]+)n ', deck, re.M)
    if len(steps) != 1 or float(steps[0][1]) != assumptions[step_key]:
        raise ValueError('Reported timestep differs from executed deck')
    breakpoint_fs = assumptions.get('minimumBreakpointFs')
    invocation = assumptions.get('analysisInvocation', 'control-tran')
    options = re.findall(r'^\.options\b.*\bminbreak\s*=\s*(\S+)', deck, re.M | re.I)
    runs = re.findall(r'^run\s*$', deck, re.M | re.I)
    if breakpoint_fs is None:
        if steps[0][0] != 'tran' or invocation != 'control-tran' or options or runs:
            raise ValueError('Unexpected transient invocation or breakpoint setting')
    else:
        if (not math.isfinite(breakpoint_fs) or breakpoint_fs <= 0
                or steps[0][0] != '.tran' or invocation != 'deck-tran/run'
                or len(runs) != 1 or options != [f'{breakpoint_fs:.17g}f']):
            raise ValueError('Reported breakpoint setting differs from executed deck')
    return re.sub(r'^(\.?tran) \S+ ', r'\1 TIMESTEP ', deck, flags=re.M)
