#!/usr/bin/env python3
"""Derive typed instruction fields from the pinned compiler and board profile."""
import argparse
import hashlib
import json
import re
import tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA, analyze
from ttl7406_probe import sha

FIELDS = {
    'OA_NUMBER': ('number', 'unsigned-long'),
    'OA_BIT1': ('bit_idx[0]', 'uint32'),
    'OA_BIT2': ('bit_idx[1]', 'uint32'),
    'OA_CODE_PTR': ('cptr', 'allocated-code-reference'),
    'OA_CODE_PTR2': ('cptr2', 'allocated-code-reference'),
    'OA_FUNC_PTR': ('net', 'net-reference'),
    'OA_FUNC_PTR2': ('net2', 'net-reference'),
    'OA_VPI_PTR': ('handle', 'vpi-reference'),
    'OA_ARR_PTR': ('array', 'array-reference'),
    'OA_STRING': ('text', 'string-reference'),
}
SPECIAL = {'%vpi_call/w': 'compile_vpi_call', '%vpi_func/r': 'compile_vpi_func_call'}


def schema(compiled, compiler):
    program = analyze(compiled)
    # These declarations synthesize executable instructions outside the table.
    if re.search(r'^\s*\S+\s+\.ufunc(?:\s|/)', compiled, re.M):
        raise ValueError('Synthesized ufunc instructions need a separate schema')
    entries = {}
    pattern = r'\{\s*"(%[^"\s]+)"\s*,\s*(of_\w+)\s*,\s*(\d+)\s*,\s*\{([^{}]+)\}\s*\}'
    for match in re.finditer(pattern, compiler):
        name, handler, count, operands = match.groups()
        types = [s.strip() for s in operands.split(',')]
        count = int(count)
        if name in entries or count > len(types) or any(t != 'OA_NONE' for t in types[count:]):
            raise ValueError('Invalid or duplicate compiler entry')
        if any(t not in FIELDS for t in types[:count]):
            raise ValueError('Unsupported operand type')
        entries[name] = dict(handler=handler, operandTypes=types[:count],
                             fields=[dict(field=FIELDS[t][0], kind=FIELDS[t][1]) for t in types[:count]])
    result = {}
    for name, count in program['opcodeCounts'].items():
        if name in entries:
            result[name] = dict(entries[name], compiledInstructions=count, construction='compile_code')
        elif name in SPECIAL:
            result[name] = dict(handler='of_VPI_CALL', compiledInstructions=count,
                                construction=SPECIAL[name], operandTypes=['special-vpi-call'],
                                fields=[dict(field='handle', kind='vpi-call-reference')])
        else:
            raise ValueError('Unmapped compiled opcode: ' + name)
    return result


def build(archive, vvp, out):
    if sha(archive) != ARCHIVE_SHA:
        raise ValueError('Changed pinned Icarus archive')
    files = {}
    with tarfile.open(archive) as tar:
        for name in ('vvp/compile.cc', 'vvp/codes.cc', 'vvp/codes.h', 'vvp/vthread.cc', 'vvp/parse.y'):
            matches = [m for m in tar.getmembers() if m.name.endswith('/' + name)]
            if len(matches) != 1:
                raise ValueError('Ambiguous pinned source')
            files[name] = tar.extractfile(matches[0]).read().decode()

    def section(name, start, end):
        text = files[name]
        a = text.index(start)
        b = text.index(end, a + len(start))
        return dict(file=name, firstLine=text[:a].count('\n') + 1, excerpt=text[a:b])

    instructions = schema(vvp.read_text(), files['vvp/compile.cc'])
    handlers = {}
    for handler in sorted({s['handler'] for s in instructions.values()} | {'of_ZOMBIE', 'of_CHUNK_LINK'}):
        text = files['vvp/vthread.cc']
        a = text.index('bool ' + handler + '(')
        b = text.index('\n}', a) + 2
        handlers[handler] = dict(file='vvp/vthread.cc', firstLine=text[:a].count('\n') + 1, excerpt=text[a:b])
    result = dict(
        qualified=False,
        scope='Typed compiler-field schema for the pinned compiled board and native handler excerpts. This is not operand observation, a transitive read/write audit or a code-immutability proof.',
        archiveSha256=ARCHIVE_SHA, compiledSha256=sha(vvp), instructions=instructions,
        implicitInstructions={'of_ZOMBIE': [], 'of_CHUNK_LINK': [dict(field='cptr', kind='nullable-allocated-code-reference')]},
        sources={n: hashlib.sha256(s.encode()).hexdigest() for n, s in files.items()},
        evidence={
            'typedUnions': section('vvp/codes.h', 'struct vvp_code_s {', '/*\n * This function clears'),
            'compilerOperandAssignments': section('vvp/compile.cc', 'void compile_code(', 'void compile_codelabel('),
            'specialVpiConstruction': section('vvp/compile.cc', 'void compile_vpi_call(', '/*\n * When the parser finds a thread'),
            'allocatorAndImplicitInstructions': section('vvp/codes.cc', 'void codespace_init(', '#ifdef CHECK_WITH_VALGRIND'),
        },
        handlers=handlers,
        requirements=[
            'Cover every allocated instruction, including currently inactive code and initialized chunk links; exclude unused capacity.',
            'Serialize only the fields selected by the native opcode schema. ZOMBIE has no operands; chunk links have only the initialized cptr operand. Do not read both union alternatives or padding.',
            'Validate code targets against allocated-slot identity before dereferencing. Distinguish an allowed null final chunk link from an invalid branch target.',
            'Scope/function operands are stored through handle by the compiler; validate subtype/ownership separately. VPI task/function forms both use of_VPI_CALL and require referenced call-object coverage.',
            'Reject unknown native opcode families, including synthesized ufunc instructions, instead of treating their payload as empty.',
            'Test restored immediate, code-target and object-reference faults plus unknown-family refusal, retaining previous PC/lifecycle controls and unchanged continuation.',
            'Audit helper calls and aliases before claiming code immutability. Neither this schema nor absence of direct cp assignments proves immutable operands or referents.',
            'Budget complete board operand evidence before long captures; do not replace required state coverage with only the currently executing PC.',
        ])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'vvp', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.archive, args.vvp, args.out)
