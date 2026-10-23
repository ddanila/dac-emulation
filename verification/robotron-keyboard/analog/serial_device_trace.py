"""Observe internal serial-driver state without changing circuit elements."""
import re

SIGNALS = [f'@q.x{gate}.q{transistor}[{quantity}]'
           for gate in ('data','clock')
           for transistor in ('output','inverter')
           for quantity in ('ic','ib','vbc','vbe','qbc','qbe')]


def observe(deck):
    for gate in ('data','clock'):
        if not re.search(rf'^X{gate} .+ TTL7406_DYNAMIC$',deck,re.M):
            raise ValueError('Requires direct dynamic driver')
    deck,count=re.subn(r'^(\.save .+)$',lambda m:m[1]+' '+' '.join(SIGNALS),deck,flags=re.M)
    if count!=1:raise ValueError('Expected one save directive')
    deck,count=re.subn(r'^(wrdata witness\.txt .+)$',lambda m:m[1]+'\nwrdata serial_device.txt '+' '.join(SIGNALS),deck,flags=re.M)
    if count!=1:raise ValueError('Expected one witness writer')
    return deck
