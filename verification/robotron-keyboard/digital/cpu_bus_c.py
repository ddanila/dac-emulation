#!/usr/bin/env python3
"""Generate the C arbitration candidate and an audited bus-start inventory."""
import re
from pathlib import Path
from io_repeat_candidate import c_core
from io_complete_candidate import c_half
from qualify import ROOT
from io_flags_candidate import replace_once
HERE = Path(__file__).resolve().parent


def generate(out):
    out.mkdir(parents=True, exist_ok=True)
    (out/'cpu_bus_half.h').write_text((HERE/'cpu_bus_half.h').read_text())
    core = c_core((ROOT/'third_party/cpu/chips/z80.h').read_text())
    (out/'candidate.h').write_text(core)
    half = c_half((HERE/'c_read_half.h').read_text())
    memory_samples = []
    states = []
    internal = []
    for line in core.splitlines():
        m = re.match(r'\s*case\s+(\w+): (.*)', line)
        if not m: continue
        body = m[2]
        if '_mread(' in body:
            targets = re.findall(r'_goto\((\w+)\)', body)
            if len(targets) != 1: raise ValueError('Ambiguous memory read successor')
            memory_samples.append(targets[0])
        if 'cpu->wz=--cpu->pc;--cpu->pc;' in body: internal.append(m[1])
        # Memory assertion states are T2. The first I/O assertion is also T2;
        # subsequent held-I/O states must never be mistaken for boundaries.
        if re.search(r'_m(?:read|write)\(', body) or (
                re.match(r'_io(?:read|write)\(', body) and '_wait()' not in body and '_gd()' not in body):
            if m[1] != 'Z80_DDFD_D_T5': states.append(m[1])
    if len(memory_samples) != len(set(memory_samples)): raise ValueError('Shared memory read successor')
    helper='static int memory_consuming(unsigned step) {switch(step){'+''.join('case '+n+':' for n in memory_samples)+'return 1;default:return 0;}}\n'
    half=replace_once(half,'static void c_read_reset',helper+'static void c_read_reset')
    old=next(line for line in half.splitlines() if 'c->pending=c_write_waiting' in line)
    expr=old.split('c->pending=',1)[1].rstrip(';')
    half=replace_once(half,old,' c->pending=memory_consuming(c->cpu.step)?5:('+expr+');')
    (out/'c_read_half.h').write_text(half)
    if len(states) < 100 or len(states) != len(set(states)):
        raise ValueError('Invalid memory/I/O microstate inventory')
    (out/'cpu_bus_states.h').write_text('static int cpu_bus_t2(const z80_t *cpu) {if(cpu->step==Z80_DDFD_D_T5)return cpu->opcode==0x36;switch(cpu->step){' +
        ''.join('case '+s+':' for s in states) + 'return 1;default:return 0;}}\n')
    if len(internal) != 8: raise ValueError('Repeat machine-cycle inventory changed')
    (out/'cpu_bus_states.h').write_text((out/'cpu_bus_states.h').read_text()+
        'static int cpu_bus_internal(unsigned step) {switch(step){case Z80_DDFD_D_T4:'+
        ''.join('case '+s+':' for s in internal)+'return 1;default:return 0;}}\n')
    return states
