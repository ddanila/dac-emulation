"""End a diagnostic prefix without changing the declared transient horizon."""
import math

def add_halt(deck,halt_ns,stop_ns):
    if stop_ns is None or not all(math.isfinite(v) for v in (halt_ns,stop_ns)) or not 0<halt_ns<stop_ns:
        raise ValueError('Diagnostic halt must precede the declared transient horizon')
    if deck.count('\nrun\n')!=1 or '\nstop when ' in deck:
        raise ValueError('Expected a single uninterrupted run')
    return deck.replace('\nrun\n',f'\nstop when time > {halt_ns:.17g}n\nrun\n',1)
