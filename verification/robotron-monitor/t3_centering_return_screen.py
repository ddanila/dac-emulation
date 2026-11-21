"""Compare conditional T3 return pulses with the source-addressed centring bridge."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import centering_bridge_check as bridge
import page9_centering_compare
import steady_supply
import t3_drive_pulse_screen as pulse
import t3_output_stage_sweep as stage
import t3_stage_refinement_screen as refinement
import transformer_candidates


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / 'reference/k7222-11/t3-centering-return-screen.json'


def replace_once(deck, old, new):
    if deck.count(old) != 1:
        raise ValueError(f'conditional stage changed: {old}')
    return deck.replace(old, new)


def case(ngspice, inputs, link_pair, coil_l_h):
    graph, parameters, candidate, parts, l3_r, l3_l, _ = inputs
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory) / 'trace.dat'
        circuit = Path(directory) / 'stage.cir'
        deck = stage.deck(graph, parameters, candidate, parts, l3_r, l3_l, trace)
        original, _ = transformer_candidates.compile_model(graph, candidate,
                                                            parameters, backend='flux')
        coupled, _ = transformer_candidates.compile_model(graph, candidate,
                                                           parameters, backend='coupled')
        deck = replace_once(deck, original, coupled)
        deck = replace_once(deck, '.ic v(h_boost)=65',
                            '.param horizontal_brightness_fraction=0.5\n'
                            'Rug1 ug1 0 1G\n.ic v(h_boost)=65')
        deck = replace_once(deck, 'reltol=.001', f'reltol={refinement.RELTOL:g}')
        deck = replace_once(deck, 'tran 100n 5m 4m', 'tran 50n 5m 4m')
        deck = replace_once(deck, '1u 20n 20n 46.5u', '1u 200n 200n 46.5u')
        if link_pair is not None:
            p = {key: value[0] for key, value in steady_supply.ASSEMBLY_BOUNDS.items()}
            if link_pair not in (0, 1) or coil_l_h <= 0:
                raise ValueError('invalid centring bridge case')
            links = [('centering_a', '0'), ('centering_c', 'p12')] if link_pair == 0 else [
                ('centering_c', '0'), ('centering_a', 'p12')]
            elements = [
                f'.param centering_coil_l_h={coil_l_h:.15g}',
                f".param centering_coil_r_ohm={p['centering_coil_r_ohm']:.15g}",
                f".param centering_r4_a_ohm={p['centering_r4_total_ohm']/2:.15g}",
                f".param centering_r4_b_ohm={p['centering_r4_total_ohm']/2:.15g}",
                f".param centering_r2_ohm={p['centering_r2_ohm']:.15g}",
                bridge.MODEL.read_text(),
                'X971 hy2 centering_a CENTERING_CHOKE',
                'X972 hy1 centering_w CENTERING_CHOKE',
                'X973 centering_a centering_b centering_w CENTERING_POT',
                'R974 centering_b centering_c {centering_r2_ohm}',
                'Vp12 p12 0 DC 12',
            ]
            elements += [f'Rlink{i} {left} {right} 1m'
                         for i, (left, right) in enumerate(links)]
            deck = replace_once(deck, 'Rhy2ref hy2 0 1G',
                                'Rhy2ref hy2 0 1G\n' + '\n'.join(elements))
        deck = replace_once(deck,
                            f'wrdata {trace} v(h_hot) v(eht)',
                            f'wrdata {trace} v(h_hot) v(h_return) '
                            'v(h_hot,h_return) v(hy2) v(eht)')
        digest = hashlib.sha256(deck.replace(str(trace), '<trace>').encode()).hexdigest()
        circuit.write_text(deck)
        process = subprocess.run([str(ngspice), '-b', str(circuit)],
                                 capture_output=True, text=True, timeout=180)
        if process.returncode or not trace.is_file() or 'tran simulation(s) aborted' in process.stdout:
            problem = [line for line in (process.stdout + '\n' + process.stderr).splitlines()
                       if any(word in line.lower() for word in ('error', 'warning', 'vector', 'wrdata'))]
            raise ValueError(f'conditional centring stage failed: {problem[-12:]}; '
                             f'log tail: {(process.stdout + process.stderr).splitlines()[-20:]}')
        with trace.open() as stream:
            header = stream.readline().split()
            rows = [list(map(float, line.split())) for line in stream if line.strip()]
    if header[:6] != ['time', 'v(h_hot)', 'v(h_return)',
                      'v(h_hot,h_return)', 'v(hy2)', 'v(eht)']:
        raise ValueError('unexpected centring trace columns')
    last = [row for row in rows if row[0] >= pulse.WINDOW_START_S]
    if not last or abs(rows[-1][0] - pulse.END_S) > 1e-9 or len(last) < 1000:
        raise ValueError('incomplete final two-line trace')
    if any(not all(map(math.isfinite, row)) for row in last):
        raise ValueError('nonfinite final two-line trace')
    if max(abs(row[1] - row[2] - row[3]) for row in last) > .0002:
        raise ValueError('inconsistent differential probe')
    collector = max(last, key=lambda row: row[1])
    differential = max(last, key=lambda row: row[3])
    return dict(link_pair='no_bridge' if link_pair is None else
                ('E1+E2' if link_pair == 0 else 'E3+E4'),
                coil_l_h=coil_l_h, normalized_deck_sha256=digest,
                final_two_line_samples=len(last),
                collector_peak_v=collector[1],
                return_at_collector_peak_v=collector[2],
                drive_at_collector_peak_v=collector[3],
                h2_at_collector_peak_v=collector[4],
                drive_peak_v=differential[3],
                h2_range_v=[min(row[4] for row in last), max(row[4] for row in last)],
                return_range_v=[min(row[2] for row in last), max(row[2] for row in last)],
                eht_at_collector_peak_v=collector[5])


def run(ngspice):
    comparison = page9_centering_compare.run()
    if not comparison['passed']:
        raise ValueError('page-9 source comparison failed')
    inputs = pulse.setup()
    low, nominal, high = (steady_supply.ASSEMBLY_BOUNDS['centering_coil_l_h'][i]
                          for i in (1, 0, 2))
    cases = [case(ngspice, inputs, None, None)]
    saved_pulse = json.loads(pulse.ROOT.joinpath(
        'reference/k7222-11/t3-drive-pulse-screen.json').read_text())
    saved_baseline = next(row for row in saved_pulse['cases']
                          if row['max_step_ns'] == 50)
    for current, old in (('collector_peak_v', 'collector_peak_v'),
                         ('return_at_collector_peak_v', 'return_at_collector_peak_v'),
                         ('drive_peak_v', 'differential_peak_v')):
        if abs(cases[0][current] - saved_baseline[old]) > .05:
            raise ValueError('no-bridge case differs from saved T3 drive pulse')
    cases += [case(ngspice, inputs, pair, inductance)
              for pair in (0, 1) for inductance in (low, nominal, high)]
    baseline = cases[0]
    max_drive_change = max(abs(row['drive_peak_v'] - baseline['drive_peak_v'])
                           for row in cases[1:])
    return dict(format='dac-monitor-t3-centering-return-screen-v1',
                qualification='conditional 4–5 ms prescribed-base stage with unverified T3 graph and 4 mH yoke; a sensitivity screen, not a source-bounded installed H2 waveform or A5 turns ratio',
                source_netlist_sha256=comparison['source_netlist_sha256'],
                centering_sheet_sha256=comparison['sheet_sha256'],
                inputs_sha256={str(path.relative_to(ROOT)): pulse.sha(path)
                               for path in (stage.GRAPH, pulse.ac.PARAMETERS,
                                            stage.TRANSCRIPTION, stage.MODELS,
                                            bridge.MODEL,
                                            page9_centering_compare.SOURCE,
                                            pulse.ROOT / 'reference/k7222-11/t3-drive-pulse-screen.json',
                                            ROOT / 'steady_supply.py',
                                            ROOT / 't3_drive_pulse_screen.py',
                                            ROOT / 't3_output_stage_sweep.py',
                                            ROOT / 't3_stage_refinement_screen.py',
                                            ROOT / 'transformer_candidates.py',
                                            ROOT / 't3_centering_return_screen.py')},
                ngspice_sha256=pulse.sha(ngspice),
                fixed_inputs=dict(r4_position=.5, coil_r_ohm=5,
                                  r4_total_ohm=1000, r2_ohm=150,
                                  yoke_l_h=.004, yoke_r_ohm=2,
                                  prescribed_base_edge_ns=200, max_step_ns=50,
                                  reltol=refinement.RELTOL),
                measured_reference='V(X2:7)-V(X2:4) = V(h_hot)-V(h_return)',
                cases=cases, maximum_drive_peak_change_from_no_bridge_v=max_drive_change,
                interpretation='The page-9 bridge couples H2 to 12P/00 through unknown chokes and link positions. These seven prescribed-drive cases show how that added path changes X2:4 and the differential pulse under one assumed T3/yoke. They do not establish the physical jumper pair, coil parameters, installed yoke geometry, or the independent source bound needed for an A5 winding ratio.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run(args.ngspice)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f"{len(result['cases'])} cases; maximum drive-peak change "
          f"{result['maximum_drive_peak_change_from_no_bridge_v']:.3f} V")
