#!/usr/bin/env python3
"""Source-accounted stage simulation. A stage bench cannot qualify a monitor.

The editable KiCad sheet is the sole connectivity input at run time. Profiles
select files, named probes and explicit finite uncertainty ranges; they contain
no substitute circuit topology. Reported times are absolute simulation times.
"""
import argparse
import array
from collections import Counter
import json
import math
from pathlib import Path
import re
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

import lab
import faults

ROOT = Path(__file__).resolve().parent
IDENTIFIER = re.compile(r'[a-zA-Z_][a-zA-Z_0-9]*\Z')


def read_profile(path):
    profile = json.loads(Path(path).read_text())
    if profile.get('format') != 'dac-monitor-profile-v1' or profile.get('qualification') != 'bounded-stage':
        raise ValueError('unsupported profile or qualification')
    lab.subcircuit_contracts(profile.get('subcircuits'))
    for key in ('schematic', 'models', 'bench', 'inventory'):
        resolved = (ROOT/profile[key]).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.is_file():
            raise ValueError('profile file outside laboratory or missing: '+key)
    extra=profile.get('additional_schematics',[])
    if not isinstance(extra,list) or len(extra)>16 or any(not isinstance(s,str) for s in extra) or len(set(extra))!=len(extra) or profile['schematic'] in extra:
        raise ValueError('invalid additional schematics')
    for name in extra:
        resolved=(ROOT/name).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.is_file() or resolved.suffix!='.kicad_sch':
            raise ValueError('additional schematic outside laboratory or missing')
    extra_models = profile.get('additional_models', [])
    if (not isinstance(extra_models, list) or len(extra_models) > 16
            or any(not isinstance(s, str) for s in extra_models)
            or len(set(extra_models)) != len(extra_models) or profile['models'] in extra_models):
        raise ValueError('invalid additional models')
    for name in extra_models:
        resolved = (ROOT/name).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.is_file() or resolved.suffix != '.cir':
            raise ValueError('additional model outside laboratory or missing')
    generated = profile.get('generated_models', {})
    if not isinstance(generated, dict) or not set(generated).issubset({profile['models'], *extra_models}):
        raise ValueError('generated model must be an included model')
    for model, document in generated.items():
        import converter_magnetics
        if not isinstance(document, str):
            raise ValueError('invalid generated model document')
        resolved = (ROOT/document).resolve()
        if not resolved.is_relative_to(ROOT) or not resolved.is_file() or resolved.suffix != '.json':
            raise ValueError('generated model document outside laboratory or missing')
        if converter_magnetics.compile_model(json.loads(resolved.read_text())) != (ROOT/model).read_text():
            raise ValueError('generated magnetic model does not match bounded parameters')
    for name, p in profile['parameters'].items():
        values = [p[k] for k in ('minimum', 'nominal', 'maximum')]
        if (not IDENTIFIER.fullmatch(name) or any(type(v) not in (int, float) or not math.isfinite(v) for v in values)
                or not 0 < values[0] <= values[1] <= values[2] or not p.get('rationale')
                or p.get('evidence') not in ('assumed-bound', 'documented-bound', 'design-derived', 'class-typical')):
            raise ValueError('invalid parameter bound: '+name)
    names = set()
    if not 1 <= len(profile['probes']) <= 127:
        raise ValueError('probe budget exceeded')
    for p in profile['probes']:
        if (not IDENTIFIER.fullmatch(p['name']) or len(p['name'])>64 or p['name'] in names or p['name'] == 'time'
                or not re.fullmatch(r'[vi]\([A-Za-z_][A-Za-z_0-9]*\)', p['expression'])
                or not p.get('unit') or len(p['unit'])>=20 or not p.get('source_id')):
            raise ValueError('invalid or duplicate probe')
        names.add(p['name'])
    if not names:
        raise ValueError('no probes')
    return profile


def source_connectivity(path, inventory, board, subcircuits=None, *, allow_floating=False):
    boards = [board] if isinstance(board,str) else board
    if not isinstance(boards,list) or not boards or any(not isinstance(b,str) for b in boards):
        raise ValueError('invalid source board scope')
    parts = {p['id']: p for p in inventory['parts']}
    tree = ET.parse(path).getroot()
    source_ids = {}
    audit_refs = {}
    audit_expected = {
        '012-6891': {'J1': '012-6891:X1', 'J2': '012-6891:X2', 'J3': '012-6891:X3'},
        '012-6921': {'J901': '012-6921:X1', 'J930': '012-6921:X3',
                     'J940': '012-6921:X4',
                     'J950': '012-6921:X5', 'J960': '012-6921:X6',
                     'J990': '012-6921:X9'},
        '012-6931': {'J910': '012-6931:X1', 'J920': '012-6931:X2',
                     'J931': '012-6931:X3'},
    }
    for c in tree.findall('./components/comp'):
        fields = {f.attrib['name']: f.text for f in c.findall('./fields/field')}
        ref=c.attrib['ref'];source_ids[ref]=fields.get('SourceId')
        audit_only=fields.get('AuditOnly')
        if audit_only is not None:
            expected = audit_expected.get(boards[0], {}) if len(boards) == 1 else {}
            if audit_only != 'source-connector' or expected.get(ref) != source_ids[ref]:
                raise ValueError('unrecognized audit-only schematic symbol')
            audit_refs[ref]=source_ids[ref].split(':')[-1]
    if audit_refs:
        if boards == ['012-6891'] and set(audit_refs) != set(audit_expected['012-6891']):
            raise ValueError('neck source connector symbols are incomplete')
        physical={name:{} for name in audit_refs.values()}
        for net in tree.findall('./nets/net'):
            name=net.attrib['name'].removeprefix('/')
            for node in net.findall('node'):
                ref=node.attrib['ref']
                if ref in audit_refs:
                    connector = physical[audit_refs[ref]]
                    if node.attrib['pin'] in connector:
                        raise ValueError('duplicate source connector pin')
                    connector[node.attrib['pin']] = name
        if boards == ['012-6891']:
            expected=json.loads((ROOT/'reference/k7222-11/assembly.json').read_text())['neck_connectors']
        else:
            source=json.loads((ROOT/'reference/k7222-11/page18-interconnect-transcription.json').read_text())
            names={'00':'0','5P':'p5','12P':'p12','22P':'p22','SYN':'sync_gate',
                   '41P':'p41','SYNCH':'h_sync','X2':'hy2','X1':'hy1',
                   'UG2':'ug2','UG4':'ug4','VID':'vid','INTENS':'intens',
                   '10.7P':'p10_7','UG1':'ug1','Y1':'y1','Y2':'y2',
                   'HRA':'contrast_adjust','HRS':'v1_base','35P':'p35',
                   'KRS':'contrast_low','KRA':'reference9'}
            expected={}
            for source_id in (source_ids[ref] for ref in audit_refs):
                connector=source_id.split(':')[-1]
                labels=({'VIDEO':'rx_video','BSYN':'rx_bsyn',
                         'INTENS':'rx_intens','00':'0'}
                        if connector == 'X9' else names)
                expected[connector]={pin:labels[label]
                                     for pin,label in source['connectors'][source_id].items()}
        if physical!=expected:
            raise ValueError('source connector pins differ from source map')
    components = lab.connectivity(path,subcircuits,ignored_refs=audit_refs,
                                  allow_floating=allow_floating)
    seen = set()
    for c in components:
        sid = source_ids[c['reference']]
        if sid not in parts or sid in seen or parts[sid]['board'] not in boards:
            raise ValueError('missing, duplicate or foreign SourceId: '+str(sid))
        if c['reference'][0] in 'VBI':
            raise ValueError('independent/behavioral sources must be outside the reference board')
        seen.add(sid)
        c['source_id'] = sid
    return components


def inventory_check(inventory):
    if inventory.get('format') != 'dac-monitor-inventory-v1':
        raise ValueError('invalid inventory format')
    ids = set()
    for p in inventory['parts']:
        if p['id'] != p['board']+':'+p['reference'] or p['id'] in ids:
            raise ValueError('duplicate or malformed inventory identity')
        ids.add(p['id'])
        if p['evidence'] not in ('documented', 'inferred', 'unresolved'):
            raise ValueError('invalid inventory evidence')
        if p['value'] is not None and (not math.isfinite(p['value']) or p['value'] <= 0):
            raise ValueError('invalid passive value')
        if p['source']['file'] != 'older.pdf' or not 1 <= p['source']['page'] <= 19:
            raise ValueError('invalid inventory source page')
    return ids


def coverage(inventory, components):
    ids = inventory_check(inventory)
    connected = [c['source_id'] for c in components]
    if len(set(connected)) != len(connected) or not set(connected) <= ids:
        raise ValueError('invalid source coverage')
    # Completeness is deliberately independent of component-count assertions.
    # Connectivity alone cannot establish models, assembly coverage or physics.
    return dict(inventoried=len(ids), boards=dict(Counter(p['board'] for p in inventory['parts'])),
                connected=len(connected), missing=sorted(ids-set(connected)),
                unresolved=[p['id'] for p in inventory['parts'] if p['evidence'] != 'documented'],
                full_monitor_qualified=False,
                remaining_gates=['complete assembly connectivity', 'all device and magnetic models',
                                 'free-running oscillation and sync lock', 'loaded supplies and thermal lifecycle',
                                 'electron optics convergence', 'service observations and held-out scenarios'])


def parameter_values(profile, changes):
    values = {name: p['nominal'] for name, p in profile['parameters'].items()}
    for name, value in changes.items():
        if name not in values or not math.isfinite(value):
            raise ValueError('unknown/nonfinite parameter: '+name)
        p = profile['parameters'][name]
        if not p['minimum'] <= value <= p['maximum']:
            raise ValueError('parameter outside declared range: '+name)
        values[name] = value
    return values


def deck(profile, components, parameters, start, stop, step, models, bench):
    if (not all(math.isfinite(x) for x in (start, stop, step)) or not 0 <= start < stop <= 120
            or not 1e-9 <= step <= 1e-4 or (stop-start)/step > 250_000 or stop/(step/10)>20_000_000):
        raise ValueError('invalid window/sample budget')
    probes = ' '.join(p['expression'] for p in profile['probes'])
    for name,count in lab.subcircuit_contracts(profile.get('subcircuits')).items():
        declarations=re.findall(r'(?im)^\.subckt\s+'+re.escape(name)+r'\s+([^\n]+)',models)
        if len(declarations)!=1 or len(declarations[0].split())!=count:
            raise ValueError('subcircuit declaration does not match pin contract: '+name)
    lines = [profile['name']+' - external stage bench, not a complete monitor']
    lines += [f'.param {k}={v:.15g}' for k, v in parameters.items()]
    lines += [' '.join([c['reference'], *c['nodes'], c['value']]) for c in components]
    # Both files are trusted local engineering source, snapshotted before use.
    lines += [models, bench, '.options reltol=0.0001 abstol=1e-12 vntol=1e-8 method=gear',
              '.control', 'set noaskquit', 'set wr_singlescale', 'set wr_vecnames', 'set numdgt=15',
              f'tran {step:.15g} {stop:.15g} {start:.15g} {step/10:.15g}',
              f'linearize {probes}', f'wrdata samples.txt {probes}', 'quit', '.endc', '.end']
    return '\n'.join(lines)+'\n'


def read_samples(path, probes, start, stop, step):
    rows = []
    with path.open() as stream:
        header = next(stream, '').split()
        if len(header) != len(probes)+1:
            raise ValueError('unexpected solver columns')
        for line in stream:
            row = [float(v) for v in line.split()]
            if (len(row) != len(probes)+1 or not all(math.isfinite(v) for v in row)
                    or rows and row[0] <= rows[-1][0]):
                raise ValueError('invalid solver samples')
            rows.append(row)
            if len(rows) > 250_001:
                raise ValueError('sample budget exceeded')
    tolerance = max(1e-12, step*1e-5)
    if (len(rows) < 2 or abs(rows[0][0]-start) > tolerance
            or abs(rows[-1][0]-stop) > tolerance):
        raise ValueError('incomplete recording window')
    return rows


def package(rows, metadata, path):
    fields = [dict(name='time', unit='s')]+metadata['probes']
    if len(rows)*len(fields)*8 > 64*1024*1024-12:
        raise ValueError('replay payload budget exceeded')
    values = array.array('d', (v for row in rows for v in row))
    if sys.byteorder != 'little':
        values.byteswap()
    payload = values.tobytes()
    report = metadata | dict(format='dac-crt-replay', version=2,
                             start_time=rows[0][0], duration=rows[-1][0]-rows[0][0],
                             end_time=rows[-1][0], chunks=[dict(kind='trace', offset=0,
                             bytes=len(payload), sha256=lab.digest(payload), rows=len(rows), fields=fields)])
    header = json.dumps(report, separators=(',', ':'), allow_nan=False).encode()
    if len(header)>1024*1024 or len(header)+len(payload)+12>64*1024*1024:
        raise ValueError('replay header/file budget exceeded')
    path.write_bytes(b'DACCRT2\n'+struct.pack('<I', len(header))+header+payload)
    return report


def run(profile_path, output, start=0, stop=.0004, step=1e-7, changes=None,
        *, fault=None, scenario=None, component_factors=None, regularization=1., runtime=None):
    solver='ngspice';runtime_receipt=None;solver_prefix=[]
    if runtime is not None:
        import monitor_runtime
        solver,runtime_receipt=monitor_runtime.verify(runtime)
        solver=str(solver)
        solver_prefix=['env','SPICE_SCRIPTS='+str(Path(runtime).resolve()/'install/share/ngspice/scripts')]
    profile = read_profile(profile_path)
    scenario_parameters=(scenario or {}).get('parameters',{})
    if scenario and (scenario.get('format')!='dac-monitor-scenario-v1' or scenario.get('model_id')!=profile['id']):
        raise ValueError('scenario/model mismatch')
    parameters = parameter_values(profile, scenario_parameters | (changes or {}))
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    try:
        files = {key: (ROOT/profile[key]).read_bytes() for key in ('schematic', 'models', 'bench', 'inventory')}
        files |= {'profile': Path(profile_path).read_bytes(), 'runner': Path(__file__).read_bytes(),
                  'lab': (ROOT/'lab.py').read_bytes(), 'optics': (ROOT/'optics.py').read_bytes(),
                  'sources': (ROOT/'sources.json').read_bytes(), 'faults': (ROOT/'faults.py').read_bytes()}
        names = dict(schematic='input.kicad_sch', models='models.cir', bench='bench.cir',
                     inventory='inventory.json', profile='profile.json', runner='reference.py',
                     lab='lab.py', optics='optics.py', sources='sources.json', faults='faults.py')
        for i,name in enumerate(profile.get('additional_schematics',[])):
            key=f'schematic_{i}';files[key]=(ROOT/name).read_bytes();names[key]=f'input-{i}.kicad_sch'
        for i,name in enumerate(profile.get('additional_models', [])):
            key=f'model_{i}'; files[key]=(ROOT/name).read_bytes(); names[key]=f'models-{i}.cir'
        if profile.get('generated_models'):
            for name in ('converter_magnetics.py', 'magnetics.py', 'transformer_candidates.py'):
                files[name] = (ROOT/name).read_bytes(); names[name] = name
            for i, document in enumerate(profile['generated_models'].values()):
                key = f'model_parameters_{i}'
                files[key] = (ROOT/document).read_bytes(); names[key] = key+'.json'
        for key,value in (('scenario',scenario),('fault',fault),('component_factors',component_factors)):
            if value is not None:
                files[key]=json.dumps(value,sort_keys=True,allow_nan=False).encode();names[key]=key+'.json'
        for key, content in files.items():
            (output/names[key]).write_bytes(content)
        if runtime_receipt is not None:
            (output/'runtime.json').write_text(json.dumps(runtime_receipt,indent=2)+'\n')
        inventory = json.loads(files['inventory'])
        inventory_check(inventory)
        lab.run_command(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml', '-o',
                         str(output/'circuit.xml'), str(output/'input.kicad_sch')], output, output/'kicad.log')
        components = source_connectivity(output/'circuit.xml', inventory, profile['board'],profile.get('subcircuits'))
        for i,_ in enumerate(profile.get('additional_schematics',[])):
            xml=output/f'circuit-{i}.xml'
            lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(xml),str(output/f'input-{i}.kicad_sch')],output,output/f'kicad-{i}.log')
            components+=source_connectivity(xml,inventory,profile['board'],profile.get('subcircuits'))
        coverage(inventory,components)
        if len({c['reference'] for c in components})!=len(components):
            raise ValueError('duplicate exported reference across sheets')
        original_components=components
        if component_factors:
            parts={p['id']:p for p in inventory['parts']}
            by_id={c['source_id']:c for c in components}
            for sid,factor in component_factors.items():
                if sid not in by_id or by_id[sid]['reference'][0] not in 'RCL':
                    raise ValueError('unknown/nonpassive tolerance target')
                tolerance=(parts[sid].get('tolerance_percent') or 0)/100
                if not math.isfinite(factor) or not 1-tolerance<=factor<=1+tolerance:
                    raise ValueError('healthy passive tolerance exceeded')
                by_id[sid]['value']=f"{faults.number(by_id[sid]['value'])*factor:.15g}"
        components=faults.parasitics(components,profile.get('parasitics',[]),parameters)
        models = '\n'.join(files[key].decode() for key in ['models'] +
                           [f'model_{i}' for i in range(len(profile.get('additional_models', [])))])
        components,models,mutation=faults.apply(components,models,fault,regularization=regularization)
        text = deck(profile, components, parameters, start, stop, step, models, files['bench'].decode())
        (output/'run.cir').write_text(text)
        log = lab.run_command([*solver_prefix,solver, '-n', '-b', 'run.cir'], output, output/'ngspice.log')
        if re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix|simulation interrupted', log):
            raise ValueError('solver diagnostics rejected')
        if runtime is not None and monitor_runtime.verify(runtime)[1]!=runtime_receipt:
            raise ValueError('runtime changed during simulation')
        rows = read_samples(output/'samples.txt', profile['probes'], start, stop, step)
        report = package(rows, dict(name=profile['name'], qualification=profile['qualification'],
                         model_id=profile['id'], probes=profile['probes'], components=components,
                         parameters=parameters, uncertainty=profile['parameters'], limitations=profile['limitations'],
                         coverage=coverage(inventory, original_components), source_pages=profile['source_pages'],
                         scenario=scenario, fault=mutation, component_factors=component_factors or {},
                         hashes={key: lab.digest(value) for key, value in files.items()} | {'deck': lab.digest(text.encode())},
                         solver=dict(tool='ngspice', version=subprocess.check_output([solver,'--version'],text=True).strip(),
                                     runtime_receipt_sha256=None if runtime_receipt is None else lab.digest((output/'runtime.json').read_bytes()),
                                     step_s=step, max_step_s=step/10, simulated_from_s=0, log_sha256=lab.digest(log.encode()))), output/'replay.mcrt')
        (output/'report.json').write_text(json.dumps(report, indent=2)+'\n')
        if profile['id'].startswith(('k7222-11-vertical','k7222-11-horizontal')):
            import service_score
            score=service_score.score(output/'samples.txt',start=start,end=stop)
            (output/'service-score.json').write_text(json.dumps(score,indent=2)+'\n')
        return report
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        (output/'FAILED.txt').write_text(str(error)+'\n')
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', type=Path, default=ROOT/'profiles/k7222-11-neck.json')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--runtime', type=Path, help='Verified monitor_runtime.py build directory')
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--stop', type=float, default=.0004)
    parser.add_argument('--step', type=float, default=1e-7)
    parser.add_argument('--parameter', action='append', default=[], metavar='NAME=VALUE')
    args = parser.parse_args()
    try:
        changes = {}
        for entry in args.parameter:
            name, value = entry.split('=', 1)
            if name in changes:
                raise ValueError('duplicate parameter '+name)
            changes[name] = float(value)
        run(args.profile, args.output, args.start, args.stop, args.step, changes, runtime=args.runtime)
        print(args.output/'replay.mcrt')
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, str(error)+'\n')


if __name__ == '__main__':
    main()
