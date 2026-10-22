#!/usr/bin/env python3
"""Generate an isolated whole-T-state I/O-read candidate; never edit vendored code."""
import re
from pathlib import Path
from qualify import ROOT

def generate(text):
    lines=text.splitlines();changed=[]
    pattern=re.compile(r'(\s*case\s+(\d+): )_wait\(\);_ioread\((cpu->bc|cpu->wz\+\+)\);(_goto\(\d+\); // .*)')
    for i,line in enumerate(lines):
        m=pattern.fullmatch(line)
        if not m:continue
        state=int(m[2]);address='cpu->wz' if m[3].endswith('++') else 'cpu->bc'
        # Assert at T2, before automatic/external waits; preserve all state transitions.
        previous=re.fullmatch(r'(\s*case\s+'+str(state-1)+r': )(_goto\('+str(state)+r'\); // .*)',lines[i-1])
        if not previous:raise ValueError('Unexpected preceding I/O state')
        # The predecessor of the assertion state is the T1 address phase.
        # ED reads enter through their opcode-dispatch case, not the adjacent
        # numeric microstate (which belongs to a different instruction).
        entry=re.compile(r'(\s*case\s+\d+: )(_goto\('+str(state-1)+r'\); // .*)')
        matches=[j for j,v in enumerate(lines) if entry.fullmatch(v)]
        if len(matches)!=1:raise ValueError('Ambiguous I/O address-preparation state')
        j=matches[0];before=entry.fullmatch(lines[j])
        lines[j]=before[1]+'_sa('+address+');'+before[2]
        lines[i-1]=previous[1]+'_ioread('+address+');'+previous[2]
        increment='cpu->wz++;' if m[3].endswith('++') else ''
        lines[i]=m[1]+'_ioread('+address+');_wait();'+increment+m[4]
        # Keep the port selected through the consuming state. _gd() still reads
        # the supplied bus value; asserting control does not overwrite DB.
        sample_address='(uint16_t)(cpu->wz-1)' if increment else address
        prefix=re.match(r'(\s*case\s+'+str(state+1)+r': )',lines[i+1])
        if not prefix:raise ValueError('Unexpected sampling state')
        lines[i+1]=lines[i+1].replace(prefix[1],prefix[1]+'_ioread('+sample_address+');',1)
        changed.append(state)
    if len(changed)!=13:raise ValueError('I/O instruction inventory changed')
    return '\n'.join(lines)+'\n'

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('out',type=Path);a=p.parse_args()
    a.out.write_text(generate((ROOT/'third_party/cpu/chips/z80.h').read_text()))
