"""Experimental steady-supply assembly. Circuit completion is not acceptance.

Converter switching is explicitly excluded. Source-addressed scan, video and
neck circuitry remain connected; no raster current or electrode voltage source
is supplied by this adapter. T3 and device families remain bounded hypotheses.
"""
import array
import bisect
import hashlib
import json
import math
import re
import struct
import subprocess
import time
from pathlib import Path
import electrothermal
import frames
import full_path_audit
import lab
import monitor_runtime
import reference
import signal_path
import transformer_candidates
import yoke_profile
import sync_lock

ROOT = Path(__file__).resolve().parent
OUTPUT_CONTRACTS = dict(HORIZONTAL_CHOKE=2, HORIZONTAL_LINEARITY=2,
    HORIZONTAL_COMPENSATION=2, HORIZONTAL_BRIGHTNESS=3, HORIZONTAL_FOCUS=3,
    T3_CANDIDATE=20)
PROBES = ('v(eht)', 'v(g2)', 'v(g4)', 'v(cathode)', 'i(Lhorizontal)',
          'i(Lvertical)', '@b.xcrt.bbeam[i]', 'v(p10_7)', 'i(v.xcrt.vheater)',
          'v(h_hot)', 'v(h_feedback)', 'v(vertical_trigger)', 'v(vertical_pulse)',
          'v(x1136.xshared.flux_b)', 'v(p5)', 'v(h_boost)', 'v(g1)',
          'v(h_control)', 'i(Vp41)', 'v(p41)', 'v(p22)', 'v(n16)',
          'v(sync_c)', 'v(h_pd)',
          'v(h_tank)', 'v(h_reactbase)', '@d1032[id]', '@d1033[id]')
PROBES += ('v(xcrt.launch_current_ua)','v(xcrt.emitted_current_ua)','@b.xcrt.bg2[i]')
# Manual service points 1–17. Keep these in the connected trace so the same
# register/scorer can assess isolated benches and every assembled candidate.
PROBES += ('v(sync_gate)', 'v(vf1)', 'v(vertical_timing)', 'v(vertical_base)',
           'v(vertical_ramp)', 'v(y2)', 'v(y1)', 'v(h_base)', 'v(h_drivebase)',
           'v(h_col)', 'v(h_drivecol)', 'v(h_outputbase)', 'v(h_sync)')

# Engineering ranges, not measured AE9VT/B31G22 parameters. The 0.4 mH
# exploratory yoke overloaded the 41 V network; 4 mH is a separate hypothesis,
# selected by electrical loading, without fitting rendered picture geometry.
ASSEMBLY_BOUNDS = {
    'width_r5_position': (.63, 0., 1., 'fraction'),
    'centering_horizontal_r4_position': (.5, 0., 1., 'fraction'),
    'brightness_position': (.5, 0., 1., 'fraction'),
    'brightness_pot_r': (10000., 5000., 10000., 'ohm'),
    'yoke_horizontal_r': (2., .5, 8., 'ohm'),
    'yoke_horizontal_l': (.004, .0004, .016, 'H'),
    'tube_anode_c': (1e-9, .25e-9, 4e-9, 'F'),
    'tube_hv_leakage': (200e6, 50e6, 800e6, 'ohm'),
    'l4_coupling': (0., 0., .999, '1'),
    'isolated_cap_leakage': (1e9, .25e9, 4e9, 'ohm'),
}


def r5_rail_scale(position):
    """R5's feedback-divider effect relative to the 41 V nominal setting.

    PDF page 10 puts R5 (1 kΩ) above R6 (2.4 kΩ), below R7 (30 kΩ).
    A fixed controller feedback voltage makes the output inversely
    proportional to R6 plus the wiper-to-bottom part of R5. R7 and total
    R5 resistance cancel in the ratio of two settings.
    """
    if type(position) not in (int,float) or not math.isfinite(position) or not 0<=position<=1:
        raise ValueError('R5 position outside physical travel')
    return (2400+1000*.63)/(2400+1000*position)


def r4_center_current(position):
    """Bounded DC yoke bias equivalent for the unresolved page-9 R4 bridge.

    The 12 V bridge feed and documented 150 ohm R2 limit its nominal
    short-circuit current to 80 mA. This is a model full-scale bound,
    not a claim that the physical bridge reaches either endpoint.
    """
    if type(position) not in (int,float) or not math.isfinite(position) or not 0<=position<=1:
        raise ValueError('R4 position outside physical travel')
    return .08*(2*position-1)


def brightness_resistances(position, total_r):
    """Page-3 external R1 from 35P through HRS to HRA.

    The 1 ohm contact floor avoids a zero-ohm SPICE element at either stop.
    """
    if (type(position) not in (int,float) or not math.isfinite(position) or not 0<=position<=1
            or type(total_r) not in (int,float) or not math.isfinite(total_r)
            or not 5000<=total_r<=10000):
        raise ValueError('external brightness pot outside declared bounds')
    return max(1.,total_r*(1-position)),max(1.,total_r*position)


def tune(assembly, selection, changes=None):
    """Bounded starting guesses from source timing, never a lock assertion."""
    line=selection['line_period_ticks']/selection['clock_hz']
    period=selection['period_ticks']/selection['clock_hz']
    guesses={'horizontal_tank_l':.00145*(line/62.5e-6)**2,
             'vertical_trim':122000*(period/.0195)-100000}
    bounds={k:(v[1],v[2]) for k,v in ASSEMBLY_BOUNDS.items()}
    for name in ('horizontal-oscillator','vertical-output','regulator5','neck'):
        profile=reference.read_profile(ROOT/'profiles'/('k7222-11-'+name+'.json'))
        bounds.update({k:(v['minimum'],v['maximum']) for k,v in profile['parameters'].items()})
    # Initialize timing once; subsequent trim trials must preserve the chosen
    # tank inductance and vertical setting, including explicit overrides.
    updates = ({} if assembly.get('timing_initialized') else guesses) | (changes or {})
    for k,v in updates.items():
        if k not in bounds or type(v) not in (int,float) or not math.isfinite(v) or not bounds[k][0]<=v<=bounds[k][1]:
            raise ValueError('assembly parameter outside declared bounds: '+k)
    assembly['parameters'].update(updates)
    assembly['timing_initialized']=True
    return dict(starting_guesses=guesses,explicit_changes=changes or {},
        rationale='LC/RC timing estimates referenced to the 16 kHz/19.5 ms S550 capture; connected lock must be measured.',
        lock_verified=False)


def select(capture, *, require_video=True):
    """One original field with an identical following field, in integer ticks."""
    result = frames.analyze(capture, fields=1, pre_roll_fields=0)
    result.update(status='incomplete', selection=None, source_content_verified=False,
                  initialization_history='assumed periodic repetition of selected original field')
    events = capture['events']; ticks = [e[0] for e in events]
    normalized = []
    for field in result['complete_fields']:
        start, end = field['start_tick'], field['end_tick']
        i = bisect.bisect_right(ticks, start)-1
        rows = [[0, *events[i][1:]]]
        for e in events[i+1:bisect.bisect_left(ticks, end)]:
            if e[1:] != rows[-1][1:]: rows.append([e[0]-start, *e[1:]])
        key = hashlib.sha256(json.dumps([end-start, rows], separators=(',', ':')).encode()).hexdigest()
        field['content_sha256'] = key
        normalized.append(rows)
    for i, (a, b) in enumerate(zip(result['complete_fields'], result['complete_fields'][1:])):
        if (a['usable'] and b['usable'] and a['content_sha256'] == b['content_sha256']
                and (not require_video or any(e[1] for e in normalized[i]))):
            result.update(status='complete', reason=None, source_content_verified=True,
                source_content_sha256=a['content_sha256'],
                selection=dict(render_start_tick=a['start_tick'], render_end_tick=a['end_tick'],
                               verification_end_tick=b['end_tick']),
                period_ticks=a['duration_ticks'], events=normalized[i])
            return result
    result['reason'] = 'No pair of adjacent identical complete fields with active VIDEO; check boot ROM and character-generator provenance.'
    return result


def heater_equilibrium():
    """Exact DC heater branch: ideal 12 V, historical R22=15 ohm, held heater R.

    No scan/beam result is inferred here. This supply simplification decouples
    heater power from flyback load; the assembled run measures it independently.
    """
    p = electrothermal.parameters()
    lo, hi = 0., 12**2/(4*15)
    for _ in range(80):
        power = (lo+hi)/2
        h, c = electrothermal.steady_temperatures(power)
        r = p['heater_cold_ohm']*(1+p['heater_alpha']*h)
        actual = (12/(15+r))**2*r
        if actual > power: lo = power
        else: hi = power
    power = (lo+hi)/2
    return dict(temperature_rise_k=list(electrothermal.steady_temperatures(power)),
                heater_power_w=power, method='steady ideal-supply series-heater branch',
                electrical_replay_verified=False)


def assembly_sheets():
    """The schematic set actually solved with ideal converter rails."""
    sheets = [(s,b,c) for s,b,c in full_path_audit.SHEETS
              if s not in ('k7222-11-converter.kicad_sch','k7222-11-power-input.kicad_sch','k7222-11-horizontal-output.kicad_sch')]
    sheets += [('k7222-11-horizontal-output.kicad_sch','012-6921',OUTPUT_CONTRACTS),
               ('1715w-output.kicad_sch','1715w',{'S37_DRIVER':3})]
    return sheets


def assemble(output, *, yoke_path=None):
    """Export and archive sheets once. No independent stage benches are included."""
    out = Path(output).resolve(); out.mkdir(parents=True, exist_ok=False)
    inv = json.loads((ROOT/'reference/k7222-11/inventory.json').read_text())
    cpu = json.loads((ROOT/'reference/1715w/output.json').read_text())
    sheets=assembly_sheets()
    components=[]; hashes={}
    def archive(name):
        raw=(ROOT/name).read_bytes(); dest=out/name
        dest.parent.mkdir(parents=True,exist_ok=True); dest.write_bytes(raw)
        hashes[name]=lab.digest(raw)
        return raw.decode()
    for name,board,contracts in sheets:
        archive('circuits/'+name); xml=out/(Path(name).stem+'.xml')
        lab.run_command(['kicad-cli','sch','export','netlist','--format','kicadxml','-o',str(xml),
                         str(out/'circuits'/name)],out,out/(Path(name).stem+'.log'))
        parts=reference.source_connectivity(xml,cpu if board=='1715w' else inv,board,contracts)
        if board=='1715w':
            for part in parts:part['nodes']=['computer_return' if n=='0' else n for n in part['nodes']]
        components += parts
    if len({c['reference'] for c in components})!=len(components):raise ValueError('duplicate assembly reference')
    params={k:v[0] for k,v in signal_path.BOUNDS.items()}
    params.update({k:v[0] for k,v in ASSEMBLY_BOUNDS.items()});models=[]
    for name in ('horizontal-oscillator','vertical-output','regulator5','neck'):
        path='profiles/k7222-11-'+name+'.json'; archive(path)
        profile=reference.read_profile(out/path)
        params.update(reference.parameter_values(profile,{}))
        for model in [profile['models'],*profile.get('additional_models',[])]:
            if model not in models:models.append(model)
    import yoke_geometry
    source=Path(yoke_path) if yoke_path is not None else yoke_geometry.DEFAULT
    raw_yoke=source.read_bytes();destination=out/'profiles/yoke.json'
    destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(raw_yoke)
    hashes['profiles/yoke.json']=lab.digest(raw_yoke)
    yoke=yoke_profile.read(destination)
    params.update(yoke['electrical'])
    models.append('circuits/signal-path-models.cir')
    texts=[archive(name) for name in models]
    # The neck's parameterized 1AD50 family also serves the sync filter; do not
    # let a duplicate fixed .model silently shadow its explicit parameters.
    texts=[re.sub(r'^\.model 1AD50_BOUND D\(IS=2n[^\n]*\n','',s,flags=re.M) for s in texts]
    for name in ('reference/k7222-11/inventory.json','reference/k7222-11/service-observations.json',
                 'reference/k7222-11/service-instrument.json',
                 'reference/1715w/output.json',
                 'reference/k7222-11/t3-winding-hypothesis.json',
                 'reference/k7222-11/t3-initial-parameters.json',
                 'reference/k7222-11/horizontal-output-transcription.json',
                 'reference/k7222-11/assembly.json',
                 'reference/k7222-11/page18-interconnect-transcription.json',
                 'reference/k7222-11/device-model-register.json',
                 'steady_supply.py',
                 'magnetics.py','transformer_candidates.py','electrothermal.py','yoke_profile.py','yoke_geometry.py',
                 'steady_acceptance.py','steady_trace.py','scan_diagnostics.py','sync_lock.py','lock_scan.py','electrical_cache.py','collection.py','beam_feedback.py','energy_ledger.py','energy_validation.py',
                 'service_score.py','calibration_contract.py','calibration_measurements.py','grid_geometry.py','phase_a_gates.py'):
        archive(name)
    return dict(components=components,parameters=params,models=texts,hashes=hashes,yoke=yoke,
                magnetic_graph=json.loads((out/'reference/k7222-11/t3-winding-hypothesis.json').read_text()),
                magnetic_parameters=json.loads((out/'reference/k7222-11/t3-initial-parameters.json').read_text()),
                coverage=reference.coverage(inv,[c for c in components if not c['source_id'].startswith('1715w:')]))


INITIAL_VOLTAGE_BOUNDS = {'eht': (0.,25000.), 'h_boost': (0.,150.),
    'h_g2raw': (0.,1000.), 'h_divtop': (0.,1000.), 'h_g1raw': (-200.,0.)}


def compensation_network(components, coupling):
    """One passive three-winding L4 hypothesis; zero reproduces uncoupled branches.

    Source terminal ordering defines an explicit same-polarity hypothesis.
    The third section remains physically shorted by the selected assembly strap.
    No factory polarity or coupling is asserted.
    """
    parts={c['source_id']:c for c in components if c['source_id'].startswith('012-6921:L4:')}
    if not parts:return [],set()
    if set(parts)!={f'012-6921:L4:{i}' for i in (1,2,3)}:raise ValueError('incomplete L4 winding assembly')
    if not math.isfinite(coupling) or not 0<=coupling<1:raise ValueError('nonpassive L4 coupling')
    lines=[]
    for i in (1,2,3):
        part=parts[f'012-6921:L4:{i}'];a,b=part['nodes']
        lines += [f'* {part["source_id"]} same-terminal-polarity hypothesis',
                  f'RL4_{i} {a} l4_internal_{i} {{horizontal_compensation_r}}',
                  f'LL4_{i} l4_internal_{i} {b} {{horizontal_compensation_l}}']
    if coupling:
        lines += [f'KL4_{a}{b} LL4_{a} LL4_{b} {coupling:.15g}' for a,b in ((1,2),(1,3),(2,3))]
    return lines,{p['reference'] for p in parts.values()}


def deck(assembly, selection, candidate, *, fields=4, max_step_s=100e-9, reltol=.005,
         linear_solver='sparse', abstol=1e-6, initial_voltages=None):
    if type(fields) is not int or not 4<=fields<=64:raise ValueError('expected 4..64 continuous settling fields')
    if not 1e-9<=max_step_s<=200e-9 or not 1e-5<=reltol<=.005:raise ValueError('invalid integration resolution')
    if linear_solver not in ('sparse','klu') or not math.isfinite(abstol) or not 1e-12<=abstol<=1e-6:
        raise ValueError('invalid linear solver/current tolerance')
    initial_voltages=dict(initial_voltages or {})
    for node,value in initial_voltages.items():
        if node not in INITIAL_VOLTAGE_BOUNDS or type(value) not in (int,float) or not math.isfinite(value) or not INITIAL_VOLTAGE_BOUNDS[node][0]<=value<=INITIAL_VOLTAGE_BOUNDS[node][1]:
            raise ValueError('invalid warm voltage guess: '+node)
    if selection['status']!='complete':raise ValueError('no static source field')
    graph=assembly.get('magnetic_graph') or json.loads((ROOT/'reference/k7222-11/t3-winding-hypothesis.json').read_text())
    parameters=assembly.get('magnetic_parameters') or json.loads((ROOT/'reference/k7222-11/t3-initial-parameters.json').read_text())
    magnetic,meta=transformer_candidates.compile_model(graph,candidate,parameters,backend='flux')
    thermal=heater_equilibrium(); period=selection['period_ticks']/selection['clock_hz']
    p={k:v[0] for k,v in ASSEMBLY_BOUNDS.items()} | assembly['parameters']
    rail_scale=r5_rail_scale(p['width_r5_position'])
    centering_current=r4_center_current(p['centering_horizontal_r4_position'])
    brightness_top,brightness_bottom=brightness_resistances(p['brightness_position'],p['brightness_pot_r'])
    yoke=assembly.get('yoke')
    if yoke is not None and yoke['inductance_field_relationship_verified']:
        if any(p[k]!=v for k,v in yoke['electrical'].items()):
            raise ValueError('geometry-derived yoke R/L cannot be overridden independently; change the frozen yoke profile')
    if yoke is not None and not yoke['inductance_field_relationship_verified']:
        yoke=dict(yoke,electrical={k:p[k] for k in yoke['electrical']})
        yoke['effective_energy_volume_m3']={a:4*math.pi*1e-7*p[f'yoke_{a}_l']/yoke['field'][f'{a}_tesla_per_amp']**2 for a in ('horizontal','vertical')}
    source_kind=assembly.get('source_kind','schematic-derived-logical')
    label=('synthetic calibration pattern' if source_kind=='synthetic-test-pattern'
           else 'native capture')
    lines=[f'Experimental steady-supply K7222 {label}; unqualified hypothesis']
    lines += [f'.param {k}={v:.15g}' for k,v in p.items()]
    l4,expanded=compensation_network(assembly['components'],p['l4_coupling'])
    lines += [' '.join([c['reference'],*c['nodes'],c['value']]) for c in assembly['components'] if c['reference'] not in expanded]
    lines += l4
    collection_report=assembly.get('collection_report')
    if collection_report is not None and abs(collection_report['period_s']-period)>1e-12:
        raise ValueError('collection period differs from native field')
    lines += assembly['models']+[magnetic,electrothermal.model(initial_rise_k=thermal['temperature_rise_k'],hold_temperature=True,collection_report=collection_report)]
    events=selection['events']+[[selection['period_ticks'],*selection['events'][0][1:]]]
    for i,signal in enumerate(('video','bsyn','intens'),1):
        # Repeat only this captured waveform. The final period is byte-for-byte
        # the selected original field; the preceding history is an assumption.
        wave=signal_path.pwl(events,i,selection['clock_hz'],period)
        endpoint=f'{period:.15g} {events[0][i]})'
        if not wave.endswith(endpoint):wave=wave[:-1]+' '+endpoint
        lines.append(f'Vlogic_{signal} logic_{signal} computer_return '+wave+' r=0')
        previous='tx_'+signal
        for j in range(4):
            node='rx_'+signal if j==3 else f'cable_{signal}_{j}'
            lines += [f'Rwire_{signal}_{j} {previous} {node} {p["cable_r"]/4}',
                      f'Cwire_{signal}_{j} {node} 0 {p["cable_c"]/4}']
            previous=node
    lines += [f'Rreturn computer_return 0 {p["return_r"]}',
        'Vp12 p12 0 12',f'Vp22 p22 0 {22*rail_scale:.15g}',
        f'Vp41 p41 0 {41*rail_scale:.15g}',f'Vn16 n16 0 {-16*rail_scale:.15g}',
        'Rcontrast_top contrast_adjust intens {contrast_r*contrast_position}',
        'Rcontrast_bottom intens contrast_low {contrast_r*(1-contrast_position)}',
        f'Rbrightness_top p35 collector_i {brightness_top:.15g}',
        f'Rbrightness_bottom collector_i contrast_adjust {brightness_bottom:.15g}',
        'Xcrt p10_7 0 cathode g1 g2 eht heater_rise cathode_rise CRT_THERMAL',
        'Ctube eht 0 {tube_anode_c}', 'Rhvleak eht 0 {tube_hv_leakage}',
        'Rhorizontal hy1 h_winding {yoke_horizontal_r}','Lhorizontal h_winding hy2 {yoke_horizontal_l}',
        f'Icentering hy2 hy1 {centering_current:.15g}',
        'Rvertical y1 v_winding {yoke_vertical_r}','Lvertical v_winding y2 {yoke_vertical_l}',
        'Rcapmid h_rectmid 0 {isolated_cap_leakage}','Ryokeleak hy1 0 {isolated_cap_leakage}',
        f'.options {linear_solver} reltol={reltol} abstol={abstol} vntol=1e-6 method=gear',
        '.save time '+' '.join(PROBES),
        *(['.ic '+' '.join(f'v({n})={v:.15g}' for n,v in sorted(initial_voltages.items()))] if initial_voltages else []),
        f'.tran {max_step_s} {period*fields:.17g} {period*(fields-4):.17g} {max_step_s}', '.end']
    assumptions=['Ideal 12 V converter input and R5-scaled 22/41/-16 V outputs; actual 5 V regulator retained.',
        'R4 horizontal centring uses a bounded DC yoke-current equivalent while the page-9 bridge links remain unresolved.',
        'External brightness R1 has page-3/page-18 terminal mapping and a handwritten 5–10 kohm class-typical value; A1 netlist comparison remains open.',
        'Periodic repetition of a captured static field initializes the circuit; no cold thermal timeline.',
        'Unmeasured yoke geometry and tube capacitance/leakage. The selected yoke profile declares whether R/L and field are jointly derived or independent.',
        'Finite 1 Gohm DC leakage at isolated C19 midpoint and horizontal yoke; not a source component.',
        'L4 uses a passive three-winding same-terminal-polarity hypothesis; coupling defaults to zero. Factory coupling/polarity remain unresolved.',
        'Exploratory solver tolerances require independent refinement; completion is not acceptance.']
    text='\n'.join(lines)+'\n'
    metadata=dict(candidate=meta,thermal=thermal,period_s=period,source_kind=source_kind,
        simulated_fields=fields,retained_fields=4,assumptions=assumptions,
        yoke=yoke,initial_voltage_guesses=initial_voltages,initialization='DC operating point with optional voltage guesses; not a periodic-state checkpoint',
        r5_equivalent=dict(source_ids=['012-6931:R5','012-6931:R6','012-6931:R7'],
            source_pdf_page=10,position=p['width_r5_position'],rail_scale=rail_scale,
            output_rails_v={'p41':41*rail_scale,'p22':22*rail_scale,'n16':-16*rail_scale},
            unchanged_input_rail_v={'p12':12},
            rule='(2400 + 1000*0.63)/(2400 + 1000*position)'),
        r4_equivalent=dict(source_ids=['012-6931:R4','012-6931:R2','012-6931:L1','012-6931:L2'],
            source_pdf_page=9,tier='class-typical',position=p['centering_horizontal_r4_position'],
            current_a=centering_current,current_bound_a=.08,
            bound_basis='12 V bridge feed / documented 150 ohm R2; nominal short-circuit limit',
            rule='current_a = 0.08 * (2 * position - 1); positive flows hy1 to hy2 through yoke'),
        external_brightness=dict(source_pdf_pages=[3,4,18],source_id='external:R1',tier='class-typical',
            position=p['brightness_position'],total_r_ohm=p['brightness_pot_r'],
            top_r_ohm=brightness_top,bottom_r_ohm=brightness_bottom,
            terminal_nodes={'E_35P':'p35','S_HRS':'collector_i','A_HRA':'contrast_adjust'},
            contact_floor_ohm=1.,source_value_note='handwritten 10 kohm with 5 kohm alternative'),
        max_step_s=max_step_s,reltol=reltol,linear_solver=linear_solver,abstol=abstol,vntol=1e-6,parameters=p,assembly_bounds=ASSEMBLY_BOUNDS)
    import collection
    metadata['collection']=dict(profile=collection.PROFILE,feedback_enabled=collection_report is not None,
        load_sha256=None if collection_report is None else lab.digest(json.dumps(collection_report,sort_keys=True,allow_nan=False).encode()),
        probe_amperes_per_volt=1e-6,launch_probe='v(xcrt.launch_current_ua)',emission_probe='v(xcrt.emitted_current_ua)',anode_probe='i(@b.xcrt.bbeam[i])')
    inputs=dict(deck_sha256=lab.digest(text.encode()),source_content_sha256=selection.get('source_content_sha256'),
                capture_sha256=assembly.get('capture_sha256'),assembly_hashes=assembly.get('hashes',{}),resolved=metadata)
    fingerprint=lab.digest(json.dumps(inputs,sort_keys=True,allow_nan=False).encode())
    metadata['experiment']=dict(format='dac-frozen-frame-experiment-v1',sha256=fingerprint,
        deck_sha256=inputs['deck_sha256'],source_content_sha256=inputs['source_content_sha256'],
        capture_sha256=inputs['capture_sha256'],source_kind=source_kind,
        assembly_hashes=inputs['assembly_hashes'])
    return text,metadata


def raw_rows(path):
    """Stream native ngspice real binary rows, rejecting truncation/nonfinite data."""
    with Path(path).open('rb') as stream:
        header=b''
        while not header.endswith(b'Binary:\n'):
            line=stream.readline()
            if not line or len(header)>1000000:raise ValueError('missing raw binary header')
            header+=line
        text=header.decode(); n=int(re.search(r'No. Variables:\s+(\d+)',text)[1])
        if not 2<=n<=4096 or 'Flags: real' not in text:raise ValueError('unsupported raw vectors')
        names=re.findall(r'^\s*\d+\s+(\S+)\s+\S+\s*$',text.split('Variables:\n')[1].split('Binary:')[0],re.M)
        if len(names)!=n or names[0]!='time':raise ValueError('unexpected raw variable table')
        declared=int(re.search(r'No. Points:\s+(\d+)',text)[1])
        unpack=struct.Struct('='+str(n)+'d'); previous=-1; count=0
        while True:
            data=stream.read(unpack.size)
            if not data:break
            if len(data)!=unpack.size:raise ValueError('truncated raw row')
            row=unpack.unpack(data)
            if not all(math.isfinite(v) for v in row) or row[0]<0 or row[0]<=previous:raise ValueError('invalid raw sample')
            previous=row[0];count+=1
            yield dict(zip(names,row))
        if count!=declared or count<2:raise ValueError('raw point count does not establish solver completion')


def solve(text, output, runtime, *, timeout_s):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    if not math.isfinite(timeout_s) or timeout_s<=0:raise ValueError('wall budget exhausted')
    binary,receipt=monitor_runtime.verify(runtime)
    (out/'run.cir').write_text(text); begin=time.monotonic(); timed_out=False
    try:
        with (out/'process.log').open('w') as log:
            process=subprocess.run([str(binary),'-n','-b','-r','trace.raw','-o','solver.log','run.cir'],
                cwd=out,stdout=log,stderr=subprocess.STDOUT,timeout=timeout_s)
            code=process.returncode
    except subprocess.TimeoutExpired:code=None;timed_out=True
    log=(out/'solver.log').read_text() if (out/'solver.log').exists() else ''
    failure=bool(re.search(r'(?i)timestep too small|aborted|fatal|error',log))
    result=dict(status='failed' if failure or timed_out or code!=0 else 'complete',
        timeout=timed_out,returncode=code,elapsed_s=time.monotonic()-begin,
        runtime=receipt,deck_sha256=lab.digest(text.encode()),
        solver_log_sha256=lab.digest(log.encode()),full_monitor_qualified=False)
    (out/'solve.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def assess(path, metadata, selection):
    """Reject incomplete, unlocked, nonperiodic or electrically implausible trials.

    The last three fields are compared on a common phase grid. This is a
    settling screen, not the tighter time-step or optical acceptance test.
    """
    period=metadata['period_s']; end=period*metadata['simulated_fields']
    start=end-3*period; line=selection['line_period_ticks']/selection['clock_hz']
    names=('v(eht)','v(g2)','v(g4)','v(cathode)','i(lhorizontal)',
           'i(lvertical)','v(x1136.xshared.flux_b)')
    sampled=[array.array('d') for _ in range(3)]
    bins=max(4096,math.ceil(period*27648000));next_tick=0;columns=len(names)
    hot_edges=[]; vertical_edges=[]; armed_h=True; armed_v=True
    previous=None; count=0; heater_j=0.; span=0.; last=None
    for row in raw_rows(path):
        count+=1; last=row
        if set(names)-set(row):raise ValueError('missing acceptance probe')
        if row['v(h_hot)']<50:armed_h=True
        if armed_h and row['v(h_hot)']>150:
            crossing=row['time']
            if previous is not None:
                crossing=previous['time']+(row['time']-previous['time'])*(150-previous['v(h_hot)'])/(row['v(h_hot)']-previous['v(h_hot)'])
            if crossing>=start:hot_edges.append(crossing)
            armed_h=False
        if row['v(vertical_pulse)']<2:armed_v=True
        if armed_v and row['v(vertical_pulse)']>5:
            if row['time']>=start:vertical_edges.append(row['time'])
            armed_v=False
        if previous is not None:
            a,b=previous['time'],row['time']
            if a>=start:
                pa=previous['v(p10_7)']*previous['i(v.xcrt.vheater)']
                pb=row['v(p10_7)']*row['i(v.xcrt.vheater)']
                heater_j+=(pa+pb)*.5*(b-a);span+=b-a
            while next_tick<3*bins:
                target=start+(next_tick+.5)*period/bins
                if target>b:break
                if target<a:raise ValueError('trace does not cover settling comparison window')
                fraction=(target-a)/(b-a)
                sampled[next_tick//bins].extend(previous[n]+fraction*(row[n]-previous[n]) for n in names)
                next_tick+=1
        previous=row
    failures=[]
    complete=last is not None and abs(last['time']-end)<=max(1e-12,end*1e-10) and next_tick==3*bins
    if not complete:failures.append('electrical trace does not reach the requested endpoint')
    variation={}
    if complete:
        for j,n in enumerate(names):
            waves=[field[j::columns] for field in sampled]
            scale=max(math.sqrt(sum(x*x for x in w)/bins) for w in waves)
            error=max(math.sqrt(sum((x-y)**2 for x,y in zip(waves[a],waves[b]))/bins)
                      for a,b in ((0,1),(0,2),(1,2)))/max(scale,1e-12)
            variation[n]=error
            if error>=.01:failures.append('nonperiodic '+n)
        if max(max(map(abs,field[6::columns])) for field in sampled)>=.5:
            failures.append('core flux outside declared B(H) screen')
        if (min(min(field[0::columns]) for field in sampled)<5000 or
                max(max(field[0::columns]) for field in sampled)>25000):
            failures.append('EHT outside exploratory 5..25 kV screen')
        for j in (4,5):
            if max(max(map(abs,field[j::columns])) for field in sampled)>10:
                failures.append('yoke current outside exploratory +/-10 A screen')
    periods=sorted(b-a for a,b in zip(hot_edges,hot_edges[1:]))
    timing=(dict(min_s=periods[0],median_s=periods[len(periods)//2],max_s=periods[-1],
                 sub_half_line_intervals=sum(v<line/2 for v in periods)) if periods else None)
    phase=None
    expected=3*period/line
    if not expected-2<=len(hot_edges)<=expected+2:
        failures.append('horizontal flyback count does not match native line timing')
    if len(hot_edges)>1:
        residual=[(t-hot_edges[0])/line-i for i,t in enumerate(hot_edges)]
        phase=max(residual)-min(residual)
        if phase>=.01:failures.append('horizontal phase drift exceeds 0.01 line')
    else:failures.append('no horizontal flyback train')
    if len(vertical_edges)!=3:failures.append('vertical reset count does not match three fields')
    elif max(abs(b-a-period) for a,b in zip(vertical_edges,vertical_edges[1:]))>=.01*line:
        failures.append('vertical reset phase drift exceeds 0.01 line')
    native_lock=sync_lock.compare(hot_edges,selection,start,end)
    if not native_lock['accepted']:failures.append('flyback does not track captured native sync edges')
    power=heater_j/span if span else None
    thermal_error=abs(power/metadata['thermal']['heater_power_w']-1) if power is not None else None
    if thermal_error is None or thermal_error>=.001:failures.append('measured heater power does not close held-temperature heat balance')
    return dict(format='dac-steady-supply-settling-v1',accepted=not failures,
        failures=failures,complete=complete,phase_samples_per_field=bins,rows=count,simulated_until_s=last['time'] if last else None,
        waveform_relative_rms_error=variation,horizontal_phase_variation_lines=phase,
        native_sync_lock=native_lock,
        horizontal_edges=len(hot_edges),vertical_edges=len(vertical_edges),horizontal_interval_summary=timing,
        heater_power_w=power,thermal_power_relative_error=thermal_error,
        full_monitor_qualified=False,numerical_refinement_verified=False)


def score_trial(trial, metadata):
    """Persist the manual comparison for the final field of a completed solve."""
    import service_score
    trial = Path(trial)
    end = metadata['period_s'] * metadata['simulated_fields']
    result = service_score.score(trial/'trace.raw', start=end-metadata['period_s'], end=end)
    destination = trial/'service-score.json'
    destination.write_text(json.dumps(result, indent=2)+'\n')
    return dict(path=str(destination), input_sha256=result['input_sha256'],
                numeric_status=result['numeric_status'],
                point_statuses={str(point['test_point']):point['status'] for point in result['points']})


def run(capture, output, runtime, *, candidate='auto', wall_budget_hours=12, changes=None, magnetic_parameters=None, solver=None, yoke_path=None, electrical_cache=None, calibration_freeze=None):
    """Archive and screen the assembled hypotheses under a single wall budget.

    No successful solve or plausible picture is promoted to a verified frame.
    Remaining acceptance requirements are reported alongside measured failures.
    """
    if not math.isfinite(wall_budget_hours) or not 0<wall_budget_hours<=12:
        raise ValueError('wall budget must be positive and at most 12 hours')
    out=Path(output).resolve();out.mkdir(parents=True,exist_ok=False)
    begin=time.monotonic();deadline=begin+wall_budget_hours*3600
    search_deadline=begin+wall_budget_hours*3600*2/3
    report=dict(format='dac-steady-supply-frame-run-v1',status='incomplete',
        qualification='experimental-connected-electrical-screen',full_monitor_qualified=False,
        specimen_validated=False,validation_reserved_s=wall_budget_hours*1200,mode='steady-supply-frame',outputs={},candidates=[],blockers=[])
    def save():
        report['elapsed_s']=time.monotonic()-begin
        (out/'run.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
    save()
    try:
        raw=Path(capture).read_bytes();(out/'input.json').write_bytes(raw)
        data=lab.parse_capture(out/'input.json');selection=select(data)
        report['capture_sha256']=lab.digest(raw)
        source_kind=data['qualification']
        synthetic_calibration=(source_kind=='synthetic-test-pattern'
                               and data.get('pattern') in ('grid','crosshatch'))
        if source_kind!='schematic-derived-logical' and not synthetic_calibration:
            raise ValueError('native firmware or labelled synthetic calibration capture required')
        report['source_kind']=source_kind
        if synthetic_calibration:report['source_pattern']=data['pattern']
        frozen_path=None;frozen=None
        if calibration_freeze is not None:
            if synthetic_calibration:
                raise ValueError('synthetic calibration must precede the native-frame freeze')
            import calibration_contract
            frozen_bytes=Path(calibration_freeze).read_bytes()
            frozen=json.loads(frozen_bytes)
            calibration_contract.verify(frozen)
            frozen_path=out/'calibration-freeze.json'
            frozen_path.write_bytes(frozen_bytes)
            report['calibration_freeze_sha256']=lab.digest(frozen_bytes)
            report['outputs']['calibration_freeze']='calibration-freeze.json'
        elif not synthetic_calibration:
            report['blockers'].append('Calibration freeze required before rendering the native frame.')
        (out/'selection.json').write_text(json.dumps(selection,indent=2)+'\n')
        report['outputs']['selection']='selection.json'
        if selection['status']!='complete':raise ValueError(selection['reason'])
        if not any(e[1] for e in selection['events']):
            raise ValueError('selected capture has no active VIDEO; check boot ROM and character generator provenance')
        assembly=assemble(out/'assembly',yoke_path=yoke_path)
        assembly['capture_sha256']=report['capture_sha256']
        assembly['source_kind']=source_kind
        if magnetic_parameters is not None:
            raw_parameters=Path(magnetic_parameters).read_bytes()
            (out/'assembly/magnetic-override.json').write_bytes(raw_parameters)
            assembly['magnetic_parameters']=json.loads(raw_parameters)
            assembly['hashes']['magnetic-override.json']=lab.digest(raw_parameters)
        report['hashes']=assembly['hashes'];report['coverage']=assembly['coverage']
        report['outputs']['assembly']='assembly'
        report['tuning']=tune(assembly,selection,changes)
        if frozen is not None:
            import calibration_contract
            selected_candidate=frozen['candidate_id'] if candidate=='auto' else candidate
            magnetic_key='magnetic-override.json' if magnetic_parameters is not None else 'reference/k7222-11/t3-initial-parameters.json'
            calibration_contract.verify_run(frozen,candidate_id=selected_candidate,
                parameters=assembly['parameters'],magnetic_sha256=assembly['hashes'][magnetic_key],
                yoke_sha256=assembly['hashes']['profiles/yoke.json'])
            report['calibration_binding']=dict(candidate_id=selected_candidate,
                magnetic_sha256=assembly['hashes'][magnetic_key],
                yoke_sha256=assembly['hashes']['profiles/yoke.json'],
                l4_coupling=assembly['parameters']['l4_coupling'],
                horizontal_tank_l=assembly['parameters']['horizontal_tank_l'])
            candidate=selected_candidate
        graph=json.loads((out/'assembly/reference/k7222-11/t3-winding-hypothesis.json').read_text())
        candidates=sorted(transformer_candidates.enumerate_candidates(graph),key=lambda c:c['id'])
        if candidate!='auto':
            candidates=[c for c in candidates if c['id']==candidate]
            if not candidates:raise ValueError('unknown transformer candidate')
        completed=[]
        for c in candidates:
            remaining=search_deadline-time.monotonic()
            if remaining<=0:report['blockers'].append('candidate search budget exhausted; final third reserved for validation');break
            entry=dict(id=c['id'],polarity=c['polarity'],attempts=[],settling={'accepted':False})
            report['candidates'].append(entry)
            for field_count in (4,8,16,32,64):
                remaining=search_deadline-time.monotonic()
                if remaining<=0:
                    report['blockers'].append('candidate search budget exhausted; final third reserved for validation');break
                text,metadata=deck(assembly,selection,c,fields=field_count,**(solver or {}))
                trial=out/c['id']/str(field_count)
                import electrical_cache as trace_cache
                result=trace_cache.solve(text,trial,runtime,timeout_s=min(remaining,1800*field_count/4),cache=electrical_cache)
                (trial/'metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
                attempt=dict(fields=field_count,solve=result,
                    outputs=dict(deck=str(trial.relative_to(out)/'run.cir'),metadata=str(trial.relative_to(out)/'metadata.json')))
                entry['attempts'].append(attempt)
                if result['status']=='complete':
                    attempt['service_score']=score_trial(trial,metadata)
                    attempt['outputs']['service_score']=str(trial.relative_to(out)/'service-score.json')
                    attempt['settling']=assess(trial/'trace.raw',metadata,selection)
                    completed.append((c,metadata,trial,attempt))
                    if attempt['settling']['complete']:
                        import steady_acceptance
                        attempt['diagnostics']=steady_acceptance.diagnose(trial,metadata,out/'input.json',assembly['yoke']['field'],search_deadline)
                else:
                    attempt['settling']=dict(accepted=False,failures=['solver failed or exceeded the trial wall budget'])
                entry['settling']=attempt['settling'];save()
                if result['status']!='complete' or entry['settling']['accepted']:break
                hard=('core flux outside declared B(H) screen','yoke current outside exploratory +/-10 A screen',
                      'no horizontal flyback train')
                if any(f in entry['settling']['failures'] for f in hard):break
                expected=3*selection['period_ticks']/selection['line_period_ticks']
                if abs(entry['settling']['horizontal_edges']/expected-1)>.1:break
            if entry['settling']['accepted']:break
        report['surviving_candidates']=[c['id'] for c in report['candidates'] if c['settling']['accepted']]
        if not report['surviving_candidates']:
            report['blockers'].append('No tested connected candidate passed lock and three-field settling.')
        report['selected_candidate']=report['surviving_candidates'][0] if report['surviving_candidates'] else None
        if completed:
            import steady_acceptance,steady_trace
            c,metadata,trial,attempt=next((v for v in completed if v[3]['settling']['accepted']),completed[-1])
            report['diagnostics']=attempt.get('diagnostics')
            if attempt['settling']['accepted'] and time.monotonic()<deadline:
                report['acceptance']=steady_acceptance.finish(assembly,selection,c,metadata,trial,out/'acceptance',runtime,solver or {},deadline,electrical_cache=electrical_cache,calibration_freeze=frozen_path,synthetic_calibration=synthetic_calibration)
                report['blockers'] += report['acceptance']['blockers']
            optical=report.get('acceptance',{}).get('checks',{}).get('optical',{})
            if optical.get('status')=='complete':
                report['outputs']['image']='acceptance/optical/frame.png'
            else:
                # A completed failed validation solve is newer evidence than its
                # search candidate. Never show the older candidate as that trial.
                diagnostic_trial,diagnostic_meta,diagnostic_settling=trial,metadata,attempt['settling']
                for check in report.get('acceptance',{}).get('checks',{}).values():
                    if check.get('solve',{}).get('status')=='complete' and 'settling' in check:
                        diagnostic_trial=Path(check['trial'])
                        diagnostic_meta=check['metadata'];diagnostic_settling=check['settling']
                if frozen_path is not None:
                    report['diagnostic_frame']=steady_acceptance.diagnostic_frame(diagnostic_trial,diagnostic_meta,out/'diagnostic-frame',diagnostic_settling,deadline)
                    report['outputs']['diagnostic_frame']='diagnostic-frame/diagnostic.json'
                    if report['diagnostic_frame']['status']=='diagnostic-only':report['outputs']['image']='diagnostic-frame/optical/frame.png'
        if 'acceptance' not in report:
            report['blockers'].append('No synchronized candidate reached collection and energy validation.')
        if not assembly['yoke']['inductance_field_relationship_verified']:
            report['blockers'].append('Yoke inductance and optical field strength remain independently assumed.')
        report['status']='blocked';save();return report
    except Exception as error:
        report.update(status='failed',failure=str(error));save();raise
