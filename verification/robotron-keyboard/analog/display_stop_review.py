#!/usr/bin/env python3
"""Validate the saved bridge stop handle against the typed callback inventory."""
from display_board_review import bundle as display_bundle


def bundle(lines,identities):
    starts=[i for i,l in enumerate(lines) if l.startswith('VR_BEGIN ')]
    if len(starts)!=1:raise ValueError('Missing or duplicate stop relationship')
    i=starts[0]
    if lines[i+1:]!=['VR_END','VA_END']:raise ValueError('Invalid stop relationship placement')
    state=display_bundle(lines[:i]+['VA_END'],identities)
    fields=lines[i].split()
    if len(fields)!=4 or fields[:2]!=['VR_BEGIN','1']:raise ValueError('Invalid stop relationship header')
    present,ident=map(int,fields[2:])
    if present not in (0,1) or ident<0 or bool(ident)!=bool(present):raise ValueError('Invalid stop relationship identity')
    callbacks=state['callbacks']['callbacks']
    executing=[cb for cb in callbacks if cb['values'][1]]
    if present:
        if len(executing)!=1:raise ValueError('Saved stop callback is not executing')
        values=executing[0]['values']
        if values[0]!=ident or values[3]!=9 or values[4]!=1 or values[6]!=1:
            raise ValueError('Saved stop handle targets wrong callback')
    elif executing:
        values=executing[0]['values']
        if values[3]!=6 or values[4]!=1 or values[6]!=1:
            raise ValueError('Missing saved delayed-stop handle')
    state['stop']={'present':bool(present),'callbackId':ident}
    return state
