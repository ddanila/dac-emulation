"""Classify scope allocation from native type names, not the is_cell operand."""
from thread_board_reachability import analyze as legacy_analyze


def analyze(text):
    program=legacy_analyze(text)
    for scope in program['scopes']:
        kind=scope['kind']
        if kind not in ('module','task','autotask','fork','autofork','begin','autobegin','generate','package','class') and not kind.startswith(('function.','autofunction.')):
            raise ValueError('Unknown native scope kind: '+kind)
        scope['isCell']=scope['automatic']
        scope['automatic']=kind in ('autotask','autofork','autobegin') or kind.startswith('autofunction.')
    program['emitted']['automaticScopes']=any(scope['automatic'] for scope in program['scopes'])
    return program
