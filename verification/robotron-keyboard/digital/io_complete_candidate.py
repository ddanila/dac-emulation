#!/usr/bin/env python3
"""Compose ordinary I/O boundaries, including write WAIT and T3 release.

Earlier retained candidates remain immutable negative controls. This generator
produces isolated source copies; it does not change either vendored CPU.
"""
import re
from c_read_candidate import generate as read_core
from io_wait_candidate import c_generate as read_half, hdl_generate as read_hdl, core_generate as read_wait_core
from io_flags_candidate import replace_once, generate as flags_core

WRITES=(922,1190,1224,1258,1287,1316,1354,1392,1420,1472,1504,1551,1603)


def c_core(text):
    text=read_core(text)
    lines=text.splitlines()
    found=[]
    for i,line in enumerate(lines):
        m=re.fullmatch(r'(\s*case\s+(\d+): )_iowrite\(([^,]+),([^;]+)\);_goto\((\d+)\);(.*)',line)
        if not m:continue
        state=int(m[2]);found.append(state)
        # Put address/data on the bus in T1; the following state asserts WR.
        pattern=re.compile(r'(\s*case\s+\d+: )(_goto\('+str(state)+r'\); // .*)')
        entries=[j for j,v in enumerate(lines) if pattern.fullmatch(v)]
        if len(entries)!=1:raise ValueError('Ambiguous write predecessor')
        j=entries[0];entry=pattern.fullmatch(lines[j])
        lines[j]=entry[1]+'_sad('+m[3]+','+m[4]+');'+entry[2]
    if tuple(found)!=WRITES:raise ValueError('Write inventory changed')
    return '\n'.join(lines)+'\n'


def c_half(text):
    text=read_half(text)
    cases=''.join('case '+str(s+1)+':' for s in WRITES)
    text=replace_once(text,'static void c_read_reset', 'static int c_write_waiting(unsigned step) {switch(step){'+cases+'return 1;default:return 0;}}\nstatic void c_read_reset')
    text=replace_once(text,'c->pending=c_read_consuming(c->cpu.step)?1:(c_read_waiting(c->cpu.step)?2:0);',
      'c->pending=c_write_waiting(c->cpu.step)?3:(((pins&(Z80_IORQ|Z80_WR))==(Z80_IORQ|Z80_WR))?4:(c_read_consuming(c->cpu.step)?1:(c_read_waiting(c->cpu.step)?2:0)));')
    text=replace_once(text,'  c->pins=z80_tick(&c->cpu,pins);', '''  uint64_t selected=pins&(UINT64_C(0xffffff)|Z80_IORQ|Z80_WR);
  c->pins=z80_tick(&c->cpu,pins);
  if(c->pending==3)c->pins=(c->pins&~(UINT64_C(0xffffff)|Z80_IORQ|Z80_WR))|selected;
  if(c->pending==4){c->pins&=~(Z80_IORQ|Z80_WR);}''')
    return text


def hdl_wrapper(text):
    text=replace_once(read_hdl(text),' && !base.write;', ';')
    for signal in ('mreq_n','iorq_n','rd_n','wr_n'):
        text=replace_once(text,'assign '+signal+'=io_cycle?',
                          'assign '+signal+'=!reset_n?1\'b1:io_cycle?')
    return text


def hdl_core(text):
    return replace_once(read_wait_core(flags_core(text)),' && !write && tstate[2]', ' && tstate[2]')
