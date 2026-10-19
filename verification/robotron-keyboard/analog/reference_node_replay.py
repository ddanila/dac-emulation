#!/usr/bin/env python3
"""Diagnostic reference-node change for the matched analog-only driver replay."""
import argparse
import json
import math
from pathlib import Path
import re
import subprocess

from analog_driver_replay import sha
from failure_evidence import solver_diagnostic
from ngspice_runtime import identify, verify

NODE = r'[A-Za-z0-9_.]+'
VOLTAGE = re.compile(r'\bv\((' + NODE + r')(?:,(' + NODE + r'))?\)', re.I)
OLD_GROUND = 'board_reference'
NEW_GROUND = 'host_receiver_gnd'


def transform(deck, shifted):
    """Admit only the fixture's explicit element forms; preserve old global ground.

    The control also expands implicit BJT substrate nodes and single-ended voltage
    observations. No XSPICE interface is admitted: its implicit reference would
    need a different transformation. This is not a general SPICE translator.
    """
    if re.search(r'\b' + OLD_GROUND + r'\b', deck, re.I):
        raise ValueError('Reserved reference node already exists')
    lines = deck.splitlines()
    if not lines or lines[0] != 'S600 firmware I/O service fixture':
        raise ValueError('Expected the analog-only service fixture')
    output = [lines[0]]
    if shifted:
        output.append('.global ' + OLD_GROUND)
    scope, control = None, False
    changed_nodes, substrates, observations = 0, 0, []

    def node(value):
        nonlocal changed_nodes
        if not re.fullmatch(NODE, value):
            raise ValueError('Unsupported node: ' + value)
        if scope and value.lower() == NEW_GROUND:
            raise ValueError('Reference node shadows a local node')
        mapped = value
        if shifted:
            if value == '0':
                mapped = OLD_GROUND
            elif value.lower() == NEW_GROUND:
                mapped = '0'
        changed_nodes += mapped != value
        return mapped

    def voltages(value):
        def replace(match):
            return f'v({node(match[1])},{node(match[2] or "0")})'
        return VOLTAGE.sub(replace, value)

    def signals(value):
        if not all(re.fullmatch(r'(?:v\(' + NODE + r'(?:,' + NODE + r')?\)|i\(' + NODE + r'\))',
                                token, re.I) for token in value.split()):
            raise ValueError('Unsupported saved expression')
        mapped = voltages(value)
        # Nutmeg's vector evaluator has no saved vector for node 0. The circuit
        # expression parser accepts V(a,0), but wrdata needs the single-ended form.
        mapped = re.sub(r'v\((' + NODE + r'),0\)', r'v(\1)', mapped)
        if re.search(r'v\(0(?:,|\))', mapped):
            raise ValueError('Ground-first observation needs separate review')
        observations.append({'original': value.split(), 'transformed': mapped.split()})
        return mapped

    for raw in lines[1:]:
        line = raw.strip()
        fields = line.split()
        if not fields or line.startswith('*'):
            output.append(raw)
            continue
        head = fields[0].lower()
        if head == '.control':
            if control or scope:
                raise ValueError('Unexpected control block')
            control = True
        elif head == '.endc':
            if not control:
                raise ValueError('Unexpected endc')
            control = False
        elif control:
            if head == 'wrdata' and len(fields) >= 3 and re.fullmatch(r'[a-z-]+\.txt', fields[1]):
                line = ' '.join(fields[:2]) + ' ' + signals(' '.join(fields[2:]))
            elif line not in ('set numdgt=17', 'set wr_singlescale', 'set wr_vecnames', 'run', 'quit'):
                raise ValueError('Unsupported control command: ' + line)
        elif head == '.subckt':
            if scope or not re.fullmatch(r'\.subckt TTL740[46]_NOMINAL a y vp g params: input_br=1', line):
                raise ValueError('Unsupported subcircuit')
            scope = fields[1]
        elif head == '.ends':
            if fields != ['.ends', scope]:
                raise ValueError('Unmatched subcircuit end')
            scope = None
        elif head == '.save':
            line = '.save ' + signals(' '.join(fields[1:]))
        elif head == '.model':
            if not re.fullmatch(r'\.model \w+ (?:D|NPN|PNP|SW|adc_bridge|dac_bridge)\([\w=.+{} -]+\)', line):
                raise ValueError('Unsupported model definition')
        elif head == '.options':
            if not all(re.fullmatch(r'(?:reltol|vntol|abstol|itl4|minbreak|trtol)=[0-9.eEf+-]+', f)
                       for f in fields[1:]):
                raise ValueError('Unsupported numerical option')
        elif head == '.tran':
            if len(fields) != 3 or not all(re.fullmatch(r'[0-9.eEn+-]+', f) for f in fields[1:]):
                raise ValueError('Unsupported transient analysis')
        elif head == '.end':
            if len(fields) != 1 or scope:
                raise ValueError('Unexpected end')
        elif head.startswith('.'):
            raise ValueError('Unsupported directive: ' + head)
        else:
            kind = head[0]
            count = {'r': 2, 'c': 2, 'l': 2, 'd': 2, 'v': 2, 'i': 2,
                     's': 4, 'e': 4, 'b': 2, 'q': 3, 'x': 4}.get(kind)
            if count is None or len(fields) <= count + 1:
                raise ValueError('Unsupported element: ' + head)
            tail = ' '.join(fields[count+1:])
            if kind in 'rclie' and not re.fullmatch(r'[0-9.eEpkmunfgt+-]+', tail):
                raise ValueError('Unsupported numeric value: ' + head)
            if kind in 'dsq' and not re.fullmatch(r'\w+', tail):
                raise ValueError('Unsupported model/instance parameters: ' + head)
            if kind == 'v' and not re.fullmatch(r'(?:[0-9.eE+-]+|(?:PWL|PULSE)\([0-9.eEpkmunf+ -]+\))', tail):
                raise ValueError('Unsupported voltage source')
            if kind == 'x' and not re.fullmatch(r'TTL740[46]_NOMINAL input_br=(?:\.01|0\.01)', tail):
                raise ValueError('Unsupported subcircuit instance')
            if kind == 'b':
                if not tail.startswith('V=') or not re.fullmatch(r'[0-9.eE+*/().-]+', VOLTAGE.sub('1', tail[2:])):
                    raise ValueError('Unsupported behavioral expression')
                tail = 'V=' + voltages(tail[2:])
            terminals = [node(f) for f in fields[1:count+1]]
            if kind == 'q':
                # INP2Q binds an omitted substrate to global node 0, even in subcircuits.
                terminals.append(node('0'))
                substrates += 1
            line = ' '.join([fields[0], *terminals, tail])
        output.append(line)
    if scope or control or output[-1] != '.end':
        raise ValueError('Unclosed deck')
    return '\n'.join(output) + '\n', {
        'shifted': shifted, 'oldGround': OLD_GROUND if shifted else '0',
        'newGround': NEW_GROUND if shifted else '0',
        'explicitSubstrates': substrates, 'mappedNodeOccurrences': changed_nodes,
        'observations': observations,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--shift-reference', action='store_true')
    args = parser.parse_args()
    source, out = args.source.resolve(), args.out.resolve()
    parent = json.loads((source/'report.json').read_text())
    if parent.get('effectiveTruncationTolerance') != 1 or parent.get('qualified') is not False:
        raise ValueError('Expected matched-control analog replay')
    if sha(source/'io.cir') != parent['artifacts']['io.cir']:
        raise ValueError('Source deck hash differs')
    deck, mapping = transform((source/'io.cir').read_text(), args.shift_reference)
    runtime, env = identify(parent['ngspiceRuntime']['executable']['path'],
                            parent['ngspiceRuntime']['spinit']['path'])
    if runtime != parent['ngspiceRuntime']:
        raise ValueError('Runtime differs')
    out.mkdir(parents=True, exist_ok=False)
    (out/'io.cir').write_text(deck)
    report = {'qualified': False, 'completed': False, 'scope': __doc__,
              'sourceDirectory': str(source), 'sourceReportSha256': sha(source/'report.json'),
              'sourceDeckSha256': sha(source/'io.cir'), 'ngspiceRuntime': runtime,
              'mapping': mapping, 'stopSeconds': parent['stopSeconds'],
              'sources': {name: sha(Path(__file__).parent/name) for name in
                          ('reference_node_replay.py', 'analog_driver_replay.py',
                           'ngspice_runtime.py', 'failure_evidence.py')},
              'boundary': 'Same branch circuit and effective options; explicit old-ground substrate and voltage references. A change of numerical coordinates can affect Newton error criteria and conditioning. Completion is not device or full-board qualification.'}
    try:
        verify(runtime)
        with (out/'ngspice.log').open('w') as log:
            process = subprocess.run([runtime['executable']['path'], '-n', '-b', 'io.cir'],
                                     cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=600)
        verify(runtime)
        report['exitCode'] = process.returncode
        log_text = (out/'ngspice.log').read_text()
        report['solverDiagnostic'] = solver_diagnostic(log_text)
        if re.search(r'^Error:', log_text, re.M):
            raise ValueError('Simulator expression or command error; inspect retained log')
        for name in ('trace.txt', 'host-trace.txt', 'driver-trace.txt', 'boundary-trace.txt'):
            if not (out/name).is_file():
                raise ValueError('Missing waveform: ' + name)
        previous, count = None, 0
        with (out/'trace.txt').open() as stream:
            header = next(stream).split()
            for line in stream:
                row = list(map(float, line.split()))
                if len(row) != 3 or not all(map(math.isfinite, row)) or (previous is not None and row[0] < previous):
                    raise ValueError('Malformed waveform')
                if previous is None and row[0] != 0:
                    raise ValueError('Missing time zero')
                previous, count = row[0], count + 1
        report.update(waveformHeader=header, waveformRows=count, lastSampleSeconds=previous)
        if not count:
            raise ValueError('Empty waveform')
        if not report['solverDiagnostic'] and abs(previous-parent['stopSeconds']) > 1e-15:
            raise ValueError('Incomplete waveform')
        report['completed'] = process.returncode == 0 and not report['solverDiagnostic']
    except Exception as error:
        report['error'] = str(error)
        raise
    finally:
        report['artifacts'] = {name: sha(out/name) for name in
                               ('io.cir', 'ngspice.log', 'trace.txt', 'host-trace.txt',
                                'driver-trace.txt', 'boundary-trace.txt') if (out/name).exists()}
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n')
    print(out/'report.json')


if __name__ == '__main__':
    main()
