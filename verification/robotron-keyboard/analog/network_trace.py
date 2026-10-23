"""Add observations of the existing cable/filter network without changing devices."""
import re
SIGNALS=['v(n_p5V)','v(n_TA_TAKT)','v(n_TA_DATEN)',
         *[f'v(L1_{i}_series)' for i in range(1,5)],
         *[f'v(n_CABLE_{n})' for n in ('TAKT','GND','5V','DATEN')],
         *[f'i(L1.{i})' for i in range(1,5)],'v(data_intent)','v(clock_intent)']
PHYSICAL_SIGNALS=SIGNALS[:-2]+['v(n_D0)','v(n_WR_N)','i(Vdriver_supply)','@bwr_low[i]','@bwr_high[i]']

def observe_network(deck, signals=SIGNALS):
    deck,count=re.subn(r'^(\.save .+)$',lambda m:m[1]+' '+' '.join(signals),deck,flags=re.M)
    if count!=1:raise ValueError('Expected one save directive')
    deck,count=re.subn(r'^(wrdata witness\.txt .+)$',lambda m:m[1]+'\nwrdata network_witness.txt '+' '.join(signals),deck,flags=re.M)
    if count!=1:raise ValueError('Expected one witness writer')
    return deck
