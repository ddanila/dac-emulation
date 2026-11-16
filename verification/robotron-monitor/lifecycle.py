#!/usr/bin/env python3
"""Continuous neck/heater characterization; not full-monitor fault diagnosis.

The DC video stimulus permits a slow thermal solve without pretending to average
an unimplemented scanning circuit. No state is reset between checkpoints.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess

import electrothermal
import faults
import lab
import reference

CHECKPOINTS = (1, 2, 5, 10, 20, 30, 60, 120, 180, 300)
PROBES = [('heater_rise', 'K', 'v(th)'), ('cathode_rise', 'K', 'v(tc)'),
          ('cathode', 'V', 'v(cathode)'), ('grid1', 'V', 'v(g1)'),
          ('grid2', 'V', 'v(g2)'), ('rail', 'V', 'v(p41)'),
          ('heater_supply_current', 'A', 'i(Vheater)'),
          ('anode_supply_current', 'A', 'i(Vanode)')]


def run(output, *, step=.05, thermal=None, fault=None):
    if step not in (.05, .025):
        raise ValueError('supported output steps are 50 ms and 25 ms')
    thermal = electrothermal.parameters(thermal)
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(format='dac-monitor-lifecycle-v1', status='incomplete',
                    qualification='bounded-neck-thermal-bench',
                    full_monitor_qualified=False, method='continuous',
                    elapsed_start_s=0, requested_end_s=300,
                    state_reset_at_checkpoints=False, restart_supported=False,
                    limitations=[
                        'External ideal heater, anode and grid supplies; historical converter and flyback absent.',
                        'DC video/intensity test; no raster, yoke, width, height or phosphor prediction.',
                        'Tube thermal/emission parameters are bounded assumptions, not B31G22 calibration.',
                        'Capacitor ESR is constant in this bench; capacitor self-heating is not implemented.',
                        'Cannot distinguish the reported monitor fault causes.'])

    def save():
        (output/'lifecycle.json').write_text(json.dumps(manifest, indent=2, allow_nan=False)+'\n')

    save()
    try:
        profile_path = reference.ROOT/'profiles/k7222-11-neck-diagnostic.json'
        profile = reference.read_profile(profile_path)
        params = reference.parameter_values(profile, {})
        # These loads are replaced by CRT_THERMAL, not silently retained in parallel.
        for name in ('beam_load', 'tube_cathode_c'):
            params.pop(name)
        files = {'input.kicad_sch': (reference.ROOT/profile['schematic']).read_bytes(),
                 'models.cir': (reference.ROOT/profile['models']).read_bytes(),
                 'inventory.json': (reference.ROOT/profile['inventory']).read_bytes(),
                 'profile.json': profile_path.read_bytes()}
        for name in ('lifecycle.py', 'electrothermal.py', 'faults.py', 'reference.py', 'lab.py', 'optics.py', 'sources.json'):
            files[name] = (reference.ROOT/name).read_bytes()
        for name, content in files.items():
            (output/name).write_bytes(content)
        inventory = json.loads(files['inventory.json'])
        reference.inventory_check(inventory)
        lab.run_command(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                         '-o', str(output/'circuit.xml'), str(output/'input.kicad_sch')], output, output/'kicad.log')
        original = reference.source_connectivity(output/'circuit.xml', inventory, profile['board'])
        components = faults.parasitics(original, profile['parasitics'], params)
        components, models, mutation = faults.apply(components, files['models.cir'].decode(), fault)
        expressions = ' '.join(p[2] for p in PROBES)
        lines = ['Continuous neck thermal bench; no historical power or scanning stages']
        lines += [f'.param {k}={v:.15g}' for k, v in params.items()]
        lines += [' '.join([c['reference'], *c['nodes'], c['value']]) for c in components]
        lines += [models, electrothermal.model(thermal), '''
Vrail external41 0 {rail_v}
Rfeed external41 wire {rail_r}
Lwire wire p41 {wire_l}
Vg1 ug1 0 -25
Vg2 ug2 0 350
Vg4 ug4 0 175
Vvideo vid 0 5
Vintensity intens 0 5
Vheater hp 0 PWL(0 0 .01 10.7)
Vanode anode 0 11000
Xcrt hp 0 cathode g1 g2 anode th tc CRT_THERMAL
.options reltol=1e-6 abstol=1e-13 vntol=1e-8 method=gear
.control
set noaskquit
set wr_singlescale
set wr_vecnames
set numdgt=15
''', f'tran {step} 300 0 {step/2}', f'linearize {expressions}',
                  f'wrdata samples.txt {expressions}', 'quit', '.endc', '.end']
        deck = '\n'.join(lines)+'\n'
        (output/'run.cir').write_text(deck)
        log = lab.run_command(['ngspice', '-b', 'run.cir'], output, output/'ngspice.log')
        if re.search(r'(?im)^\s*(?:error|fatal|warning)|timestep too small|singular matrix|simulation interrupted', log):
            raise ValueError('solver diagnostics rejected')
        rows = reference.read_samples(output/'samples.txt', PROBES, 0, 300, step)
        checkpoints = []
        for t in CHECKPOINTS:
            row = min(rows, key=lambda r: abs(r[0]-t))
            if abs(row[0]-t)>step*1e-5:
                raise ValueError('missing lifecycle checkpoint')
            checkpoints.append(dict(elapsed_s=t, trace_time_s=row[0],
                                    values=dict(zip((p[0] for p in PROBES), row[1:]))))
        manifest.update(status='complete', completed_end_s=rows[-1][0],
                        trace_time_origin_elapsed_s=0, checkpoints=checkpoints,
                        fields=[dict(name=n, unit=u, expression=e) for n,u,e in PROBES],
                        thermal_parameters=thermal, thermal_bounds=electrothermal.BOUNDS,
                        parameters=params, fault=mutation, coverage=reference.coverage(inventory, original),
                        solver=dict(version=subprocess.check_output(['ngspice','--version'],text=True).strip(),
                                    output_step_s=step, max_step_s=step/2),
                        hashes={name: lab.digest(content) for name,content in files.items()} |
                               {name: lab.digest((output/name).read_bytes()) for name in
                                ('run.cir','samples.txt','circuit.xml','ngspice.log')})
        save()
        return manifest
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        manifest['failure'] = str(error)
        save()
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--step', type=float, default=.05)
    parser.add_argument('--fault', type=Path, help='JSON fault definition')
    args = parser.parse_args()
    report = run(args.output, step=args.step,
                 fault=json.loads(args.fault.read_text()) if args.fault else None)
    print(report['status'], report['qualification'])
