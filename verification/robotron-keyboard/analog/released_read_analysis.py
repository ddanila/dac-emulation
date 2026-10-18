"""Conservative architectural flag-flow check for the S600 released I/O read."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ROM_SHA = '4b54891c02a8ec279e2b8aec03489a961fc8647e08ad2036dcf82d0634bf7273'
CONDITIONS = {'NZ': 0x40, 'Z': 0x40, 'NC': 1, 'C': 1,
              'PO': 4, 'PE': 4, 'P': 0x80, 'M': 0x80}


def analyze(rom, operations):
    # IN B,(C); EX AF,AF'; LD B,H. Only B and non-carry F can depend
    # on the read. B is overwritten before use; F moves into the alternate bank.
    if rom[0x57:0x5b] != bytes.fromhex('ed400844'):
        raise ValueError('Released-read discard sequence differs')
    if rom[0x32:0x36] != bytes.fromhex('cbf8ed40'):
        raise ValueError('Other input read no longer forces A15 high')
    pcs = sorted(operations)
    following = dict(zip(pcs, pcs[1:]))
    pending = [(0x5b, 0, 0xfe)]
    seen = set()
    observed = set()
    while pending:
        pc, flags, alternate = pending.pop()
        state = (pc, flags, alternate)
        if state in seen:
            continue
        seen.add(state)
        if pc not in operations:
            raise ValueError(f'Branch enters an undecoded instruction: {pc:04x}')
        op = operations[pc]
        branch, fall = None, True

        def consume(mask):
            observed.add((pc, mask))
            if flags & mask:
                raise ValueError(f'Released input affects flags read at {pc:04x}: {op}')

        if pc == 0x57:
            # Analyze every later read as a fresh arbitrary value as well.
            pending.append((0x5b, alternate, (flags & 1) | 0xfe))
            continue
        if op == "EX AF,AF'":
            flags, alternate = alternate, flags
        elif op.startswith(('JP ', 'JR ')):
            target = op.split(' ', 1)[1].split(',')
            branch = int(target[-1][:-1], 16) & 2047
            if len(target) == 2:
                consume(CONDITIONS[target[0]])
            else:
                fall = False
        elif op.startswith('DJNZ '):
            branch = int(op[5:-1], 16) & 2047
        elif op in ('EXX', 'DI', 'EI', 'NOP'):
            pass
        elif op.startswith('LD '):
            if op in ('LD A,I', 'LD A,R'):
                flags &= 1
        elif op.startswith(('RES ', 'SET ', 'OUT ')):
            pass
        elif op.startswith('IN '):
            if pc != 0x34 or op != 'IN B,(C)':
                raise ValueError('Unexpected input instruction')
            flags &= 1
        elif op.startswith('BIT '):
            flags &= 1
        elif op.startswith(('INC ', 'DEC ')):
            if op.split()[1] not in ('BC', 'DE', 'HL', 'SP', 'IX', 'IY'):
                flags &= 1
        elif op.startswith(('ADC ', 'SBC ')):
            consume(1)
            flags = 0
        elif op.startswith(('AND ', 'OR ', 'XOR ', 'CP ', 'SUB ')) or op == 'NEG':
            flags = 0
        elif op.startswith('ADD '):
            flags = flags & 0xc4 if op.startswith('ADD HL,') else 0
        elif op in ('RLCA', 'RRCA'):
            flags &= 0xc4
        elif op in ('RLA', 'RRA'):
            consume(1)
            flags &= 0xc4
        elif op.startswith(('RL ', 'RR ')):
            consume(1)
            flags = 0
        elif op.startswith(('RLC ', 'RRC ', 'SLA ', 'SRA ', 'SRL ')):
            flags = 0
        else:
            raise ValueError(f'Unsupported instruction at {pc:04x}: {op}')
        if branch is not None:
            pending.append((branch, flags, alternate))
        if fall:
            pending.append((following[pc], flags, alternate))
    return {'observableDependencyFound': False, 'abstractStates': len(seen),
            'visitedOffsets': sorted({state[0] for state in seen}),
            'instructions': {f'{pc:04x}': operations[pc] for pc in sorted({state[0] for state in seen})},
            'flagReads': [{'offset': pc, 'mask': mask} for pc, mask in sorted(observed)]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rom', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    rom = args.rom.read_bytes()
    if hashlib.sha256(rom).hexdigest() != ROM_SHA:
        raise SystemExit('Expected the identified standard S600 ROM')
    with tempfile.TemporaryDirectory() as temporary:
        exe = Path(temporary) / 'disassemble'
        subprocess.run(['cc', str(HERE / 'released_read_disassemble.c'), '-o', str(exe)], check=True)
        decoded = subprocess.check_output([str(exe), str(args.rom)], text=True)
    operations = {int(line[:4], 16): line[5:] for line in decoded.splitlines()}
    result = analyze(rom, operations)
    result.update(qualified=False, romSha256=ROM_SHA,
                  scope='Conservative architectural control/data dependency check for bytes read at ROM offset 0057; all conditional paths explored, including later arbitrary released reads.',
                  assumptions=['Execution enters the identified read with otherwise equal architectural state.',
                               'Matching external inputs at the driven read; fixed read-only ROM mirrored by its low 11 address bits.',
                               'Documented instruction behavior; no asynchronous interrupts, reset divergence, electrical faults or metastability.'],
                  method='Track arbitrary non-carry flags through both flag banks. Reject any tainted condition/carry use or unsupported reachable instruction. Data registers remain equal after the verified B overwrite.',
                  instructionReference='https://www.zilog.com/docs/z80/um0080.pdf (UM008011-0816)',
                  boundary='Flag registers can remain different. This is not full internal-state equivalence, a CPU implementation proof, analog input model, timing qualification or waiver of CPU_DI_UNKNOWN.')
    files = [Path(__file__), HERE / 'released_read_disassemble.c', ROOT / 'third_party/cpu/chips/z80dasm.h']
    result['sources'] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    args.out.write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
