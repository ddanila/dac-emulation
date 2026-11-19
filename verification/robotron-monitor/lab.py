#!/usr/bin/env python3
"""Local KiCad -> ngspice -> bounded museum replay, standard-library only."""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

from optics import DEFAULTS, landing, deposit

ROOT = Path(__file__).resolve().parent
MAGIC = b'DACCRT1\n'
FIELDS = [('time', 's'), ('collector', 'V'), ('anode', 'V'), ('focus', 'V'),
          ('horizontal', 'A'), ('vertical', 'A'), ('cathode', 'V'),
          ('beam', 'A'), ('x', 'm'), ('y', 'm'), ('sigma', 'm'), ('landed', 'bool')]
PROBES = 'v(collector) v(anode) v(focus) i(L3) i(L4) v(cathode) @b1[i]'
LIMITATIONS = [
    'Experimental driven flyback fixture; NOT the historical K7222 circuit.',
    'Ideal horizontal/vertical drive; no sync separator, oscillator or power converter.',
    'Linear transformer; no saturation, historical winding model or device calibration.',
    'Parameterized paraxial electron optics; estimated yoke and phosphor properties.',
    'Accelerated heater stimulus; not a physical warm-up time prediction.',
]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def run_command(argv, directory, log, *, timeout=600):
    # Preserve diagnostics even on timeout and allow progress inspection without
    # keeping a long solver's output in the parent process throughout the run.
    with log.open('w') as stream:
        result = subprocess.run(argv, cwd=directory, stdout=stream,
                                stderr=subprocess.STDOUT, text=True, timeout=timeout)
    if result.returncode:
        raise ValueError(f'{argv[0]} failed; see {log}')
    return log.read_text()


def subcircuit_contracts(subcircuits):
    if subcircuits is None:
        return {}
    if not isinstance(subcircuits, dict) or any(
        not isinstance(name, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', name)
        or type(count) is not int or not 2 <= count <= 32
        for name, count in subcircuits.items()
    ) or len({name.lower() for name in subcircuits}) != len(subcircuits):
        raise ValueError('invalid subcircuit pin contracts')
    return subcircuits


def connectivity(xml_path, subcircuits=None, *, ignored_refs=()):
    subcircuits = subcircuit_contracts(subcircuits)
    ignored_refs=set(ignored_refs)
    root = ET.parse(xml_path).getroot()
    pins, names = {}, set()
    for net in root.findall('./nets/net'):
        name = net.attrib['name'].removeprefix('/')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*|0', name):
            raise ValueError(f'Use simple explicit net labels; unsupported net {name}')
        if name in names:
            raise ValueError(f'duplicate net {name}')
        names.add(name)
        for node in net.findall('node'):
            key = (node.attrib['ref'], node.attrib['pin'])
            if key in pins:
                raise ValueError(f'duplicate pin {key}')
            pins[key] = name
    if '0' not in names:
        raise ValueError('circuit requires ground net 0')
    components = []
    for comp in root.findall('./components/comp'):
        ref = comp.attrib['ref']
        if ref in ignored_refs:
            ignored_refs.remove(ref)
            continue
        value = comp.findtext('value', '')
        if re.fullmatch(r'X\d+',ref) and subcircuits and value in subcircuits:
            count=subcircuits[value]
        elif not re.fullmatch(r'[RCLDQVBI]\d+', ref):
            raise ValueError(f'{ref}: unsupported primitive; use numbered R,C,L,D,Q,V,B,I or an explicitly declared X subcircuit')
        else:
            count = 3 if ref[0] == 'Q' else 2
        nets = [pins.get((ref, str(i))) for i in range(1, count+1)]
        if None in nets or not value or any(c in value for c in '\r\n'):
            raise ValueError(f'{ref}: missing pins/value or multiline value')
        # Do not silently discard extra pins or four-terminal devices.
        if sum(1 for r, _ in pins if r == ref) != count:
            raise ValueError(f'{ref}: wrong pin count')
        components.append({'reference': ref, 'nodes': nets, 'value': value})
    if not components:
        raise ValueError('empty schematic')
    if ignored_refs:raise ValueError('ignored component reference is absent')
    return components


def parse_capture(path):
    if path.stat().st_size > 64*1024*1024:
        raise ValueError('capture file budget exceeded')
    data = json.loads(path.read_text())
    if not isinstance(data,dict) or data.get('format') not in ('dac-monitor-input-v1','dac-monitor-input-v2'):
        raise ValueError('unsupported input capture')
    if data['format']=='dac-monitor-input-v2':
        if (data.get('clock_hz')!=179712000 or data.get('signals')!=['VIDEO','BSYN','INTENS']
            or data.get('board_revision')!='1.93.310412.6/04'
            or data.get('qualification') not in ('schematic-derived-logical','synthetic-test-pattern')
            or not isinstance(data.get('time_origin'),dict)
            or not isinstance(data.get('assumptions'),list)
            or len(data['assumptions'])>20
            or any(not isinstance(s,str) or len(s)>1000 for s in data['assumptions'])):
            raise ValueError('unsupported v2 signal contract')
        origin=data['time_origin']
        if data['qualification']=='schematic-derived-logical':
            if (type(origin.get('boot_cpu_ticks')) is not int or not 0<=origin['boot_cpu_ticks']<=200000000
                or type(origin.get('character_phase_ticks')) is not int or not 0<=origin['character_phase_ticks']<104):
                raise ValueError('invalid capture time origin')
        elif origin.get('dot_tick')!=0 or type(origin.get('dot_tick')) is not int:
            raise ValueError('invalid pattern time origin')
    hz = data.get('clock_hz')
    events = data.get('events')
    if type(hz) is not int or not 1 <= hz <= (100_000_000 if data['format']=='dac-monitor-input-v1' else 200_000_000) or not isinstance(events, list) or not 2 <= len(events) <= 2_000_000:
        raise ValueError('invalid capture clock/event count')
    previous = -1
    for event in events:
        if (not isinstance(event, list) or len(event) != 4 or
            any(type(v) is not int for v in event) or event[0] <= previous or
            event[0]/hz > 1 or any(v not in (0, 1) for v in event[1:])):
            raise ValueError('invalid capture event')
        previous = event[0]
    if events[0][0] != 0:
        raise ValueError('capture must start at tick zero')
    return data


def build_deck(components, models, stop, step, changes, capture=None):
    values = {c['reference']: c['value'] for c in components}
    for ref, value in changes.items():
        if ref not in values or not value or '\n' in value or '\r' in value:
            raise ValueError(f'unknown component or invalid override: {ref}')
        values[ref] = value
    if capture:
        if 'V4' in changes:
            raise ValueError('capture and V4 override are mutually exclusive')
        hz = capture['clock_hz']
        if capture['events'][-1][0]/hz < stop:
            raise ValueError('capture does not cover the simulation interval')
        # Fixture has only video input. BSYN/INTENS are retained in the capture,
        # not falsely interpreted as a simulation of the missing receiver stages.
        last = capture['events'][0][1]
        points = [f'0 {last*5}']
        for ticks, video, _, _ in capture['events'][1:]:
            t = ticks/hz
            if video != last:
                if t > 0:
                    points.append(f'{max(0,t-1e-9):.12g} {last*5}')
                points.append(f'{t:.12g} {video*5}')
                last = video
        values['V4'] = 'PWL('+' '.join(points)+')'
    lines = ['Experimental CRT fixture - not a K7222 reconstruction']
    for c in components:
        lines.append(' '.join([c['reference'], *c['nodes'], values[c['reference']]]))
    lines.extend([models, '.options reltol=0.0001 abstol=1e-11 vntol=1e-7 method=gear', '.save all @b1[i]',
                  '.control', 'set noaskquit', 'set wr_singlescale', 'set wr_vecnames',
                  'set numdgt=15', f'tran {step:.12g} {stop:.12g} 0 {step/10:.12g}',
                  f'linearize {PROBES}', f'wrdata samples.txt {PROBES}', 'quit', '.endc', '.end'])
    return '\n'.join(lines)+'\n'


def samples(path, stop):
    result = []
    with path.open() as stream:
        next(stream)
        for line in stream:
            row = [float(v) for v in line.split()]
            if len(row) != 8 or not all(math.isfinite(v) for v in row):
                raise ValueError('invalid solver sample')
            if result and row[0] <= result[-1][0]:
                raise ValueError('non-monotonic solver time')
            result.append(row)
            if len(result) > 250_001:
                raise ValueError('solver sample budget exceeded')
    if len(result) < 2 or result[0][0] != 0 or abs(result[-1][0]-stop) > 1e-8:
        raise ValueError('incomplete transient')
    return result


def package(rows, metadata, output):
    width, height = 160, 112
    phosphor = [0.]*(width*height)
    trace = array.array('d')
    chunks, payload = [], bytearray()

    def append(kind, raw, **extra):
        chunks.append(dict(kind=kind, offset=len(payload), bytes=len(raw), sha256=digest(raw), **extra))
        payload.extend(raw)

    next_frame, previous, deposited, beam_energy = 0., rows[0][0], 0., 0.
    last_frame = 0.
    for t, collector, anode, focus, ih, iv, cathode, beam in rows:
        dt = t-previous
        previous = t
        # Match electrical B1 sign: positive current leaves EHT into the tube.
        beam = max(0., beam)
        x, y, sigma, visible = landing(anode-cathode, focus-cathode, ih, iv)
        energy = beam*max(0., anode-cathode)*dt
        beam_energy += energy
        if visible:
            correction = math.exp((t-last_frame)/DEFAULTS['phosphor_tau_s'])
            deposited += deposit(phosphor, width, height, x, y, sigma,
                                 energy*DEFAULTS['light_efficiency']*correction)/correction
        trace.extend((t, collector, anode, focus, ih, iv, cathode, beam, x, y, sigma, float(visible)))
        # Decay every sample is unnecessarily expensive. Exact exponential
        # between deposition times uses a common scale, implemented below by
        # decaying on every frame and correcting deposits for their age.
        if t >= next_frame or t == rows[-1][0]:
            elapsed = t - last_frame
            factor = math.exp(-elapsed/DEFAULTS['phosphor_tau_s'])
            phosphor = [v*factor for v in phosphor]
            pixels = bytes(min(255, round(255*(1-math.exp(-v*2e8)))) for v in phosphor)
            append('frame', pixels, time=t, width=width, height=height)
            last_frame = t
            next_frame = t+.0005
    if sys.byteorder != 'little':
        trace.byteswap()
    append('trace', trace.tobytes(), rows=len(rows), fields=[dict(name=n, unit=u) for n,u in FIELDS])
    metadata |= dict(format='dac-crt-replay', version=1, duration=rows[-1][0],
                     parameters=DEFAULTS, chunks=chunks, limitations=LIMITATIONS,
                     qualification='experimental-fixture', energy=dict(beam_j=beam_energy, deposited_light_j=deposited))
    header = json.dumps(metadata, separators=(',', ':'), allow_nan=False).encode()
    output.write_bytes(MAGIC+struct.pack('<I',len(header))+header+payload)
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schematic', type=Path, default=ROOT/'circuits/fixture.kicad_sch')
    parser.add_argument('--models', type=Path, default=ROOT/'circuits/fixture-models.cir')
    parser.add_argument('--output', type=Path, required=True, help='new directory; never overwrites an experiment')
    parser.add_argument('--name', default='Driven flyback baseline')
    parser.add_argument('--duration', type=float, default=.02)
    parser.add_argument('--step', type=float, default=1e-6)
    parser.add_argument('--set', action='append', default=[], metavar='REF=VALUE')
    parser.add_argument('--capture', type=Path)
    args = parser.parse_args()
    if not (math.isfinite(args.duration) and math.isfinite(args.step) and
            0 < args.duration <= 1 and 1e-9 <= args.step <= 1e-5 and args.duration/args.step <= 250_000):
        parser.error('duration/step exceeds finite simulation budget (250000 samples)')
    args.output.mkdir(parents=True, exist_ok=False)
    directory = args.output.resolve()
    try:
        snapshots = {'schematic':args.schematic.read_bytes(), 'models':args.models.read_bytes(),
                     'optics':(ROOT/'optics.py').read_bytes(), 'packager':Path(__file__).read_bytes(),
                     'sources':(ROOT/'sources.json').read_bytes()}
        if args.capture:
            snapshots['capture'] = args.capture.read_bytes()
        inputs = {name:digest(data) for name,data in snapshots.items()}
        (directory/'input.kicad_sch').write_bytes(snapshots['schematic'])
        (directory/'models.cir').write_bytes(snapshots['models'])
        for name, filename in [('optics','optics.py'), ('packager','lab.py'), ('sources','sources.json')]:
            (directory/filename).write_bytes(snapshots[name])
        if args.capture:(directory/'input.json').write_bytes(snapshots['capture'])
        changes = {}
        for change in args.set:
            ref, value = change.split('=', 1)
            if ref in changes:
                raise ValueError(f'duplicate override {ref}')
            changes[ref] = value
        run_command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',
                     str(directory/'circuit.xml'), str(directory/'input.kicad_sch')], directory, directory/'kicad.log')
        components = connectivity(directory/'circuit.xml')
        (directory/'connectivity.json').write_text(json.dumps(components, indent=2)+'\n')
        capture = parse_capture(directory/'input.json') if args.capture else None
        deck = build_deck(components, snapshots['models'].decode(), args.duration, args.step, changes, capture)
        (directory/'run.cir').write_text(deck)
        log = run_command(['ngspice','-b','run.cir'], directory, directory/'ngspice.log')
        if re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix|simulation interrupted', log):
            raise ValueError('solver diagnostics rejected; see ngspice.log')
        rows = samples(directory/'samples.txt', args.duration)
        inputs['deck'] = digest(deck.encode())
        effective_components = [dict(c, value=changes.get(c['reference'], c['value'])) for c in components]
        if capture:
            for c in effective_components:
                if c['reference'] == 'V4':
                    c['value'] = 'Timed VIDEO PWL (see hashed run.cir)'
        metadata = dict(name=args.name, source='Experimental fixture alongside K7222 reference research',
                        hashes=inputs, changes=changes, components=effective_components,
                        solver=dict(tool='ngspice', log_sha256=digest(log.encode()),
                                    version=subprocess.check_output(['ngspice','--version'],text=True).strip(),
                                    step_s=args.step, max_step_s=args.step/10),
                        input={'description':capture.get('provenance'), 'input_sha256':capture.get('input_sha256')} if capture else 'Synthetic ideal drive and video sources')
        report = package(rows, metadata, directory/'replay.mcrt')
        (directory/'report.json').write_text(json.dumps(report,indent=2)+'\n')
        print(directory/'replay.mcrt')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        (directory/'FAILED.txt').write_text(str(error)+'\n')
        parser.exit(1, f'{error}\n')


if __name__ == '__main__':
    main()
