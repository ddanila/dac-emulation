"""Restrict integration-method experiments to an otherwise byte-preserved replay."""
import re


def prepare(deck, method):
    if method not in ('original', 'gear', 'trap1'):
        raise ValueError('Unknown integration comparison')
    if method == 'original':
        return deck, {'selection': method, 'addedOptions': None}
    # This deliberately admits only the recorded fixture's simple option syntax.
    # Reject competing options anywhere, including control blocks or continuations.
    if re.search(r'\b(method|maxord)\b', deck, re.I):
        raise ValueError('Source already sets integration method/order')
    if re.search(r'^\s*(?:\.include|\.inc|\.lib|alter|altermod|set|option|options)\b',
                 deck, re.I | re.M):
        # The fixture has only output-format set commands; these cannot set method.
        for line in deck.splitlines():
            if re.match(r'^\s*(?:\.include|\.inc|\.lib|alter|altermod|set|option|options)\b', line, re.I):
                if line not in ('set numdgt=17', 'set wr_singlescale', 'set wr_vecnames'):
                    raise ValueError('Unsupported external or control configuration')
    if deck.count('.control\n') != 1:
        raise ValueError('Expected one recorded control block')
    option = '.options method=gear maxord=2' if method == 'gear' else '.options method=trap maxord=1'
    if deck.count('\nrun\n') != 1:
        raise ValueError('Expected one recorded run command')
    changed = deck.replace('.control\n', option+'\n.control\n', 1)
    changed = changed.replace('\nrun\n', '\nrun\noption\n', 1)
    return changed, {'addedControlCommand': 'option', 'selection': method, 'addedOptions': option,
                     'boundary': 'Numerical integration comparison, not device damping or physical qualification'}


def refine_step(deck, divisor):
    """Refine the recorded .tran step without changing its endpoint or stimulus."""
    from decimal import Decimal
    if divisor not in (1,2,4):
        raise ValueError('Unsupported timestep divisor')
    matches=list(re.finditer(r'^\.tran ([0-9]+(?:\.[0-9]+)?)n ([0-9.eE+-]+)$',deck,re.M))
    if len(matches)!=1 or len(re.findall(r'^\s*\.tran\b',deck,re.I|re.M))!=1:
        raise ValueError('Expected one simple recorded .tran command')
    match=matches[0]
    step=Decimal(match[1])
    if step!=50:raise ValueError('Expected the 50 ns matched replay source')
    refined=step/divisor
    changed=deck if divisor==1 else deck[:match.start(1)]+str(refined)+deck[match.end(1):]
    return changed, {'divisor':divisor,'sourceStepNs':float(step),'stepNs':float(refined),
                     'derivedMinimumStepSeconds':float(refined*Decimal('1e-20')),
                     'boundary':'ngspice traninit derives delmin as 1e-11 times the maximum step; refinement also lowers that numerical floor. Circuit tolerances and stimulus are unchanged.'}
