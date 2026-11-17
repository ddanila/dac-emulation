#!/usr/bin/env python3
"""One optical frame under an explicit periodic electrical-history assumption.

This bypasses cold phosphor buildup analytically. It does not establish circuit
settling, thermal equilibrium, or that an electrical trace came from a monitor.
"""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys
import time
import beam_render
import phosphor


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def equilibrium(renderer, start_s, end_s):
    """Fold all arrivals from this emission period, then solve E = q E + D.

    The cold render contains arrivals through end_s. Late electrons from the
    same emission period are folded back into their phase, accounting for the
    previous periods' arrivals near the beginning of the displayed field.
    """
    period = end_s-start_s
    if not renderer.completed or not math.isfinite(period) or period <= 0:
        raise ValueError('expected a complete positive electrical period')
    if renderer.window_start_s != start_s or renderer.surface.time != end_s:
        raise ValueError('period does not end at the rendered boundary')
    p = renderer.surface.p
    wrapped = phosphor.Surface(p, start_s=start_s)
    # Use (start, end] for arrivals exactly on a boundary, consistent with
    # Renderer._drain(end) including that event in the endpoint snapshot.
    arrivals = sorted((start_s+((e[0]-start_s) % period or period), e[2], e[3], e[4])
                      for e in renderer.events)
    for when, x, y, joules in arrivals:
        wrapped.deposit(when, x, y, joules)
    wrapped.snapshot(end_s)
    denominator = -math.expm1(-period/p['tau_s'])
    energy = array.array('d', ((a+b)/denominator for a, b in
                             zip(renderer.surface.energy, wrapped.energy)))
    deposited = renderer.surface.deposited_j+wrapped.deposited_j
    clipped = renderer.surface.clipped_j+wrapped.clipped_j
    terminal = renderer.incident_j
    accounted = renderer.intercepted_j+(deposited+clipped)/p['efficiency']
    residual = abs(accounted-terminal)/max(terminal, 1e-30)
    if residual > 1e-8:
        raise ValueError('periodic deposition does not close the kinetic energy ledger')
    linear = array.array('f', (e/(p['tau_s']*a) for e, a in zip(energy, renderer.surface.areas)))
    def srgb(v):
        return 12.92*v if v <= .0031308 else 1.055*v**(1/2.4)-.055
    display = bytes(round(255*srgb(min(1, max(0, v*p['exposure_m2_per_w'])))) for v in linear)
    return dict(format='dac-periodic-phosphor-state-v1', period_s=period,
                boundary_time_s=end_s, parameters=p.copy(), energy_j=list(energy),
                initialization='analytic-periodic-phosphor',
                assumed_periodic_electrical_history=True, late_arrivals_folded=len(arrivals),
                energy=dict(initial_stored_optical_j=sum(energy), final_stored_optical_j=sum(energy),
                            deposited_optical_j=deposited, emitted_optical_j=deposited,
                            clipped_optical_j=clipped, terminal_kinetic_j=terminal,
                            intercepted_kinetic_j=renderer.intercepted_j,
                            kinetic_balance_relative_error=residual)), linear, display


def run(trace, output, *, surface=None, field=None, step_m=.0002,
        max_dt_s=1/27648000, row_budget=100000000, bundle_budget=100000000):
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=False)
    report = dict(format='dac-periodic-frame-v1', status='incomplete',
                  qualification='experimental-periodic-optical-bench',
                  full_monitor_qualified=False, specimen_validated=False,
                  electrical_settling_verified=False, thermal_equilibrium_verified=False,
                  assumed_periodic_electrical_history=True, outputs={})
    def save():
        (out/'frame.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    save()
    begin = time.monotonic()
    try:
        trace = Path(trace)
        before = digest(trace)
        shutil.copyfile(trace, out/'input.csv')
        if digest(out/'input.csv') != before:
            raise ValueError('trace changed during import')
        hashes = {'input.csv': before}
        for name in (*beam_render.model_hashes(), 'periodic_frame.py'):
            src = Path(__file__).parent/name
            shutil.copyfile(src, out/name)
            hashes[name] = digest(out/name)
        first = last = None
        count = 0
        for row in beam_render.iter_trace(out/'input.csv', byte_budget=16*1024**3,
                                         row_budget=row_budget):
            if first is None:
                first = row
            last = row
            count += 1
        renderer = beam_render.Renderer(surface=surface, field=field, backend='compiled',
                                        step_m=step_m, max_dt_s=max_dt_s, bundle_budget=bundle_budget)
        renderer.render_stream(beam_render.iter_trace(out/'input.csv', byte_budget=16*1024**3,
                               row_budget=row_budget), [first[0], last[0]],
                               on_frame=lambda frame: None, row_budget=row_budget)
        if digest(out/'input.csv') != before:
            raise ValueError('archived trace changed during rendering')
        state, linear, display = equilibrium(renderer, first[0], last[0])
        phosphor.png(out/'frame.png', renderer.surface.p['width'], renderer.surface.p['height'], display)
        if sys.byteorder != 'little':
            linear.byteswap()
        (out/'frame.f32').write_bytes(linear.tobytes())
        (out/'periodic-state.json').write_text(json.dumps(state, separators=(',', ':'), allow_nan=False)+'\n')
        report.update(status='complete', electrical_rows=count, hashes=hashes,
                      render=renderer.report(), energy=state['energy'],
                      elapsed_s=time.monotonic()-begin, late_arrivals_folded=state['late_arrivals_folded'],
                      outputs={name: dict(path=name, sha256=digest(out/name))
                               for name in ('frame.png', 'frame.f32', 'periodic-state.json')},
                      linear_format=dict(dtype='little-endian float32', unit='W/m^2', order='row-major',
                                         width=renderer.surface.p['width'], height=renderer.surface.p['height']))
        save()
        return report
    except Exception as error:
        report.update(failure=str(error), elapsed_s=time.monotonic()-begin)
        save()
        raise




def cached_run(trace, output, cache, **options):
    """Reuse a hash-verified optical artifact, never an electrical checkpoint."""
    import tempfile
    import trajectory_native
    resolved=dict(surface=phosphor.Surface(options.get('surface')).p,
                  field=beam_render.trajectory.parameters(options.get('field')),
                  step_m=options.get('step_m',.0002),max_dt_s=options.get('max_dt_s',1/27648000),
                  row_budget=options.get('row_budget',100000000),bundle_budget=options.get('bundle_budget',100000000))
    inputs=dict(trace_sha256=digest(trace),models=beam_render.model_hashes(),
                periodic_source=digest(__file__),settings=resolved,backend=trajectory_native.build()[1])
    key=hashlib.sha256(json.dumps(inputs,sort_keys=True,allow_nan=False).encode()).hexdigest()
    cache=Path(cache).resolve();cache.mkdir(parents=True,exist_ok=True)
    entry=cache/key;hit=entry.exists()
    if not hit:
        with tempfile.TemporaryDirectory(prefix='pending-',dir=cache) as temp:
            staging=Path(temp)/'artifact'
            run(trace,staging,**options)
            (staging/'cache-key.json').write_text(json.dumps(inputs,sort_keys=True)+'\n')
            staging.rename(entry)
    if json.loads((entry/'cache-key.json').read_text())!=inputs:raise ValueError('optical cache key mismatch')
    report=json.loads((entry/'frame.json').read_text())
    if report.get('status')!='complete' or report.get('electrical_settling_verified') is not False:
        raise ValueError('invalid cached optical qualification')
    expected_hashes={'input.csv':inputs['trace_sha256'],**inputs['models'],'periodic_frame.py':inputs['periodic_source']}
    if report['hashes']!=expected_hashes:raise ValueError('optical cache model mismatch')
    render=report['render']
    if (render['parameters']!=resolved['surface'] or render['field_parameters']!=resolved['field'] or
        render['trajectory_step_m']!=resolved['step_m'] or render['max_interval_s']!=resolved['max_dt_s'] or
        render['backend_build']!=inputs['backend']):raise ValueError('optical cache settings mismatch')
    for name,value in report['hashes'].items():
        path=(entry/name).resolve()
        if not path.is_relative_to(entry) or digest(path)!=value:raise ValueError('corrupt optical cache input')
    for item in report['outputs'].values():
        path=(entry/item['path']).resolve()
        if not path.is_relative_to(entry) or digest(path)!=item['sha256']:raise ValueError('corrupt optical cache output')
    if report['hashes']['input.csv']!=inputs['trace_sha256']:raise ValueError('optical cache trace mismatch')
    out=Path(output).resolve()
    if out.exists():raise FileExistsError(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='optical-copy-',dir=out.parent) as temp:
        staging=Path(temp)/'artifact';shutil.copytree(entry,staging)
        report['cache']=dict(key=key,hit=hit,scope='optical-artifact-only')
        (staging/'frame.json').write_text(json.dumps(report,indent=2)+'\n')
        staging.rename(out)
    return report


def compare(base, refined, *, spatial=False):
    """Compare single periodic linear frames, with intact input/model archives.

    No alignment, gain fitting or exposure normalization. This checks optical
    refinement of the SAME electrical field, not electrical settling.
    """
    import image_acceptance
    def read(directory):
        root=Path(directory).resolve(); manifest=digest(root/'frame.json')
        report=json.loads((root/'frame.json').read_text())
        if report.get('status')!='complete':raise ValueError('incomplete periodic frame')
        for name,value in report['hashes'].items():
            path=(root/name).resolve()
            if not path.is_relative_to(root) or digest(path)!=value:raise ValueError('periodic input/model hash mismatch')
        for name,entry in report['outputs'].items():
            path=(root/entry['path']).resolve()
            if not path.is_relative_to(root) or digest(path)!=entry['sha256']:raise ValueError('periodic output hash mismatch')
        surface=phosphor.Surface(report['render']['parameters'])
        raw=(root/'frame.f32').read_bytes()
        if len(raw)!=4*len(surface.areas):raise ValueError('invalid periodic linear dimensions')
        pixels=array.array('f');pixels.frombytes(raw)
        if sys.byteorder!='little':pixels.byteswap()
        if any(not math.isfinite(v) or v<0 for v in pixels) or not any(pixels):
            raise ValueError('invalid or dark periodic image')
        if digest(root/'frame.json')!=manifest:raise ValueError('periodic manifest changed')
        return report,surface,pixels,manifest
    a,sa,pa,ha=read(base);b,sb,pb,hb=read(refined)
    if a['hashes']!=b['hashes']:raise ValueError('optical comparison needs identical electrical input and model sources')
    if a['render']['field_parameters']!=b['render']['field_parameters']:
        raise ValueError('optical field geometry changed')
    if spatial:
        if any(sa.p[k]!=sb.p[k] for k in sa.p if k not in ('width','height')):
            raise ValueError('phosphor parameters changed')
        if sb.p['width']!=2*sa.p['width'] or sb.p['height']!=2*sa.p['height']:
            raise ValueError('expected exactly 2x spatial refinement')
        pb=image_acceptance.project(pb,sb,sa)
    elif sa.p!=sb.p:raise ValueError('image dimensions/parameters changed')
    if not spatial and (b['render']['trajectory_step_m']>a['render']['trajectory_step_m']/2
                        or b['render']['max_interval_s']>a['render']['max_interval_s']/2):
        raise ValueError('expected at least 2x trajectory and temporal refinement')
    if spatial and (b['render']['trajectory_step_m']>a['render']['trajectory_step_m']
                    or b['render']['max_interval_s']>a['render']['max_interval_s']):
        raise ValueError('spatial comparison cannot coarsen trajectory/time resolution')
    relative=image_acceptance.error(pa,pb,sa.areas)
    residual=max(a['energy']['kinetic_balance_relative_error'],b['energy']['kinetic_balance_relative_error'])
    if not math.isfinite(residual) or residual<0:raise ValueError('invalid optical energy ledger')
    result=dict(format='dac-periodic-frame-comparison-v1',accepted=relative<.02 and residual<.01,
        scope='spatial-refinement' if spatial else 'optical-integration-refinement',
        relative_l2_error=relative,maximum_energy_residual=residual,
        base_manifest_sha256=ha,refined_manifest_sha256=hb,
        electrical_settling_verified=False,full_monitor_qualified=False,specimen_validated=False)
    return result


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--trace', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--assume-periodic', action='store_true', required=True,
                   help='Explicitly assume preceding identical electrical periods; no circuit qualification')
    p.add_argument('--cache',type=Path,help='Hash-verified optical artifact cache; not electrical state')
    p.add_argument('--field-parameters',type=Path,help='Explicit reduced field parameters, archived in render metadata')
    p.add_argument('--width',type=int,default=480)
    p.add_argument('--height',type=int,default=360)
    p.add_argument('--trajectory-step-m',type=float,default=.0002)
    p.add_argument('--max-interval-s',type=float,default=1/27648000)
    a = p.parse_args()
    operation=run if a.cache is None else lambda trace,out,**kw: cached_run(trace,out,a.cache,**kw)
    operation(a.trace, a.output,surface=dict(width=a.width,height=a.height),
        step_m=a.trajectory_step_m,max_dt_s=a.max_interval_s,
        field=json.loads(a.field_parameters.read_text()) if a.field_parameters else None)
