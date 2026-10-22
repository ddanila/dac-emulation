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
    (out/'cpu_bus_pins.h').write_text((HERE/'cpu_bus_pins.h').read_text())
    core = c_core((ROOT/'third_party/cpu/chips/z80.h').read_text())
    (out/'candidate.h').write_text(core)
    step_block=core.split('// <% extra_step_defines',1)[1].split('// %>',1)[0]
    (out/'cpu_bus_steps.h').write_text(step_block.strip()+'\n')
    half = c_half((HERE/'c_read_half.h').read_text())
    memory_samples = []
    memory_wait = []
    memory_kinds = []
    states = []
    internal = []
    extra_internal = []
    for line in core.splitlines():
        m = re.match(r'\s*case\s+(\w+): (.*)', line)
        if not m: continue
        body = m[2]
        if '_mread(' in body or '_mwrite(' in body:
            memory_wait.append(m[1])
            memory_kinds.append((m[1],1 if '_mread(' in body else 2))
        if '_mread(' in body:
            targets = re.findall(r'_goto\((\w+)\)', body)
            if len(targets) != 1: raise ValueError('Ambiguous memory read successor')
            memory_samples.append(targets[0])
        if re.search(r'_z80_(?:add|adc|sbc)16\(',body):
            target=int(re.search(r'_goto\((\d+)\)',body)[1])
            extra_internal += [m[1],str(target+3)]
        if 'cpu->pc+=(int8_t)cpu->dlatch;' in body:extra_internal.append(m[1])
        if 'cpu->wz=--cpu->pc;--cpu->pc;' in body: internal.append(m[1])
        # Memory assertion states are T2. The first I/O assertion is also T2;
        # subsequent held-I/O states must never be mistaken for boundaries.
        if re.search(r'_m(?:read|write)\(', body) or (
                re.match(r'_io(?:read|write)\(', body) and '_wait()' not in body and '_gd()' not in body):
            if m[1] != 'Z80_DDFD_D_T5': states.append(m[1])
    if len(memory_samples) != len(set(memory_samples)): raise ValueError('Shared memory read successor')
    helper='static int memory_consuming(unsigned step) {switch(step){'+''.join('case '+n+':' for n in memory_samples)+'return 1;default:return 0;}}\n'
    helper+='static int memory_waiting(unsigned step) {switch(step){'+''.join('case '+n+':' for n in memory_wait)+'return 1;default:return 0;}}\n'
    half=replace_once(half,'static void c_read_reset',helper+'static void c_read_reset')
    old=next(line for line in half.splitlines() if 'c->pending=c_write_waiting' in line)
    expr=old.split('c->pending=',1)[1].rstrip(';')
    half=replace_once(half,old,' c->pending=memory_consuming(c->cpu.step)?5:(memory_waiting(c->cpu.step)?6:('+expr+'));')
    half=replace_once(half,'int pending;', 'int pending,fetch_ready;')
    helper='static int fetch_waiting(unsigned step) {switch(step){case Z80_M1_T2:case Z80_DDFD_M1_T2:case Z80_CB_M1_T2:case Z80_ED_M1_T2:case 1638:case 1644:case 1657:return 1;default:return 0;}}\n'
    half=replace_once(half,'static void c_read_reset',helper+'static void c_read_reset')
    half=replace_once(half,'c->pins=z80_init(&c->cpu);c->pending=0;', 'c->pins=z80_init(&c->cpu);c->pending=0;c->fetch_ready=0;')
    half=replace_once(half,' c->pending=memory_consuming', ' if(c->fetch_ready){uint64_t wait=pins&Z80_WAIT;pins=z80_tick(&c->cpu,pins&~Z80_WAIT)|wait;c->fetch_ready=0;}\n c->pending=fetch_waiting(c->cpu.step)?7:memory_consuming')
    half=replace_once(half,' if(c->pending){', ' if(c->pending==7){c->fetch_ready=!(pins&Z80_WAIT);c->pending=0;return c->pins=pins;}\n if(c->pending){')
    (out/'c_read_half.h').write_text('#include \"cpu_bus_steps.h\"\n'+half)
    if len(states) < 100 or len(states) != len(set(states)):
        raise ValueError('Invalid memory/I/O microstate inventory')
    (out/'cpu_bus_states.h').write_text('static int cpu_bus_t2(const z80_t *cpu) {if(cpu->step==Z80_DDFD_D_T5)return cpu->opcode==0x36;switch(cpu->step){' +
        ''.join('case '+s+':' for s in states) + 'return 1;default:return 0;}}\n')
    if len(internal) != 8: raise ValueError('Repeat machine-cycle inventory changed')
    (out/'cpu_bus_states.h').write_text((out/'cpu_bus_states.h').read_text()+
        'static int cpu_bus_internal(unsigned step) {switch(step){case Z80_DDFD_D_T4:'+
        ''.join('case '+s+':' for s in internal+extra_internal)+'return 1;default:return 0;}}\n')
    (out/'cpu_bus_states.h').write_text((out/'cpu_bus_states.h').read_text()+
        'static inline int cpu_bus_memory_kind(const z80_t *cpu) {switch(cpu->step){'+
        ''.join('case '+n+':return '+('cpu->opcode==0x36?1:0' if n=='Z80_DDFD_D_T5' else str(k))+';' for n,k in memory_kinds)+'default:return 0;}}\n')
    return states
