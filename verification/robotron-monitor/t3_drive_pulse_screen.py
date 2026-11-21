"""Measure both T3 drive terminals in the conditional prescribed-drive stage."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import tempfile

import t3_ac_loss_candidate_screen as ac
import t3_loaded_return_screen as returns
import t3_output_stage_sweep as stage
import t3_stage_refinement_screen as refinement
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
REFINEMENT = ROOT / 'reference/k7222-11/t3-stage-refinement-screen.json'
END_S = .005
WINDOW_START_S = END_S - 2 * refinement.PERIOD_S


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def setup():
    parameters = json.loads(ac.PARAMETERS.read_text())
    if parameters != ac.candidate_parameters():
        raise ValueError('conditional T3 parameters changed')
    graph = json.loads(stage.GRAPH.read_text())
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == tp17.CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:' + name] for name in tp17.SOURCE_PARTS]
    selected, pins = returns.variant_parts(parts, transcription['ports'],
                                           True, 'hv_only_grounded')
    return graph, parameters, candidate, selected, l3_r, l3_l, pins


def case(ngspice, inputs, step_ns, expected_sha):
    graph, parameters, candidate, parts, l3_r, l3_l, _ = inputs
    with tempfile.TemporaryDirectory() as directory:
        trace = Path(directory) / 'trace.dat'
        circuit = Path(directory) / 'stage.cir'
        original, _ = transformer_candidates.compile_model(graph, candidate,
                                                            parameters, backend='flux')
        coupled, _ = transformer_candidates.compile_model(graph, candidate,
                                                           parameters, backend='coupled')
        deck = stage.deck(graph, parameters, candidate, parts, l3_r, l3_l, trace)
        t3 = next(part for part in parts if part['source_id'] == '012-6921:T3')
        flux = f'v({t3["reference"].lower()}.xshared.flux_b)'
        first_a = f'v({t3["reference"].lower()}.xshared.l0)'
        # Xshared's w0n is a port alias; ngspice exposes its mapped tap.
        first_b = f'v({t3["nodes"][1]})'
        changes = [
            (original, coupled),
            ('.ic v(h_boost)=65',
             '.param horizontal_brightness_fraction=0.5\n'
             'Rug1 ug1 0 1G\n.ic v(h_boost)=65'),
            ('reltol=.001', f'reltol={refinement.RELTOL:g}'),
            ('tran 100n 5m 4m', f'tran {step_ns}n 5m 4m'),
            ('1u 20n 20n 46.5u', '1u 200n 200n 46.5u'),
            ('i(Lhorizontal) v(h_boost)',
             'i(Lhorizontal) v(h_boost) ' + ' '.join((flux, first_a, first_b))),
        ]
        for old, new in changes:
            if deck.count(old) != 1:
                raise ValueError('conditional stage deck changed')
            deck = deck.replace(old, new)
        normalized = hashlib.sha256(deck.replace(str(trace), '<trace>').encode()).hexdigest()
        original_probe = f'wrdata {trace} v(h_hot) v(eht)'
        new_probe = (f'wrdata {trace} v(h_hot) v(h_return) '
                     f'v(h_hot,h_return) v(eht)')
        if deck.count(original_probe) != 1:
            raise ValueError('stage trace location changed')
        deck = deck.replace(original_probe, new_probe)
        circuit.write_text(deck)
        process = subprocess.run([str(ngspice), '-b', str(circuit)],
                                 capture_output=True, text=True, timeout=120)
        if (process.returncode or not trace.is_file() or
                'tran simulation(s) aborted' in process.stdout):
            problem = [line for line in (process.stdout+'\n'+process.stderr).splitlines()
                       if any(word in line.lower() for word in ('error', 'warning', 'vector', 'wrdata'))]
            raise ValueError('conditional stage did not complete: '+str(problem[-12:]))
        with trace.open() as stream:
            header = stream.readline().split()
            rows = [list(map(float, line.split())) for line in stream if line.strip()]
    if header[:5] != ['time', 'v(h_hot)', 'v(h_return)',
                      'v(h_hot,h_return)', 'v(eht)']:
        raise ValueError('unexpected drive trace columns')
    if not rows or abs(rows[-1][0] - END_S) > 1e-9:
        raise ValueError('incomplete drive trace')
    last = [row for row in rows if row[0] >= WINDOW_START_S]
    if len(last) < 1000 or any(not all(math.isfinite(x) for x in row) for row in last):
        raise ValueError('invalid final two-line trace')
    columns = {name: i for i, name in enumerate(header)}
    if not {flux, first_a, first_b} <= columns.keys():
        raise ValueError('missing first-winding flux or voltage probes')
    loss_ohm = parameters['core']['loss_ohm']['value']
    voltage = lambda row: row[columns[first_a]] - row[columns[first_b]]
    flux_values = [row[columns[flux]] for row in last]
    signed_voltage_integral = sum(
        (voltage(a) + voltage(b)) * (b[0] - a[0]) / 2
        for a, b in zip(last, last[1:]))
    mean_square_voltage = sum(
        (voltage(a)**2 + voltage(b)**2) * (b[0] - a[0]) / 2
        for a, b in zip(last, last[1:])) / (last[-1][0] - last[0][0])
    first_turns = parameters['groups']['drive'][0]['turns']['value']
    core_area = parameters['core']['area_m2']['value']
    flux_voltage_error = (signed_voltage_integral / (first_turns * core_area)
                          - (flux_values[-1] - flux_values[0]))
    if abs(flux_voltage_error) > .0005:
        raise ValueError('first-winding voltage does not integrate to core flux')
    difference_error = max(abs(row[1] - row[2] - row[3]) for row in last)
    if difference_error > .0002:
        raise ValueError('differential voltage probe is inconsistent')
    collector_peak = max(last, key=lambda row: row[1])
    drive_peak = max(last, key=lambda row: row[3])
    return dict(max_step_ns=step_ns, normalized_reference_deck_sha256=normalized,
                saved_refinement_deck_sha256=expected_sha,
                same_deck_as_saved_refinement=normalized == expected_sha,
                sample_count=len(rows), final_two_line_samples=len(last),
                final_window_s=[WINDOW_START_S, END_S],
                collector_peak_v=collector_peak[1],
                return_at_collector_peak_v=collector_peak[2],
                differential_at_collector_peak_v=collector_peak[3],
                differential_peak_v=drive_peak[3],
                differential_minimum_v=min(row[3] for row in last),
                eht_at_collector_peak_v=collector_peak[4],
                maximum_probe_difference_error_v=difference_error,
                conditional_core_flux_t=dict(minimum=min(flux_values),
                                             maximum=max(flux_values),
                                             peak_to_peak=max(flux_values)-min(flux_values),
                                             maximum_absolute=max(map(abs, flux_values))),
                loss_window_s=[last[0][0], last[-1][0]],
                first_winding_voltage_reference=f'{first_a}-{first_b}',
                flux_voltage_integral_error_t=flux_voltage_error,
                first_winding_voltage_rms_v=math.sqrt(mean_square_voltage),
                loss_shunt_ohm=loss_ohm,
                mean_loss_shunt_power_w=mean_square_voltage/loss_ohm)


def run(ngspice):
    saved = json.loads(REFINEMENT.read_text())
    selected = {(row['prescribed_base_edge_ns'], row['max_step_ns']): row
                for row in saved['cases']}
    inputs = setup()
    cases = [case(ngspice, inputs, step,
                  selected[(200, step)]['normalized_deck_sha256'])
             for step in (50, 25)]
    changes = {key: abs(cases[1][key] - cases[0][key]) / abs(cases[0][key])
               for key in ('collector_peak_v', 'return_at_collector_peak_v',
                           'differential_peak_v')}
    return dict(
        format='dac-monitor-t3-drive-pulse-screen-v1',
        qualification='conditional 4-5 ms prescribed-base stage under the unverified T3 graph and return; diagnostic voltage reference only, not A5 turns or connected Phase B score',
        inputs_sha256={str(path.relative_to(ROOT)): sha(path)
                       for path in (ac.PARAMETERS, ac.SOURCE, ac.LOSS,
                                    stage.GRAPH, stage.TRANSCRIPTION,
                                    returns.RETURN_READ, stage.MODELS,
                                    REFINEMENT, ROOT/'magnetics.py',
                                    ROOT/'transformer_candidates.py',
                                    ROOT/'t3_output_stage_sweep.py',
                                    ROOT/'t3_stage_refinement_screen.py',
                                    ROOT/'t3_loaded_return_screen.py',
                                    Path(__file__).resolve())},
        ngspice_sha256=sha(ngspice),
        candidate_id=inputs[2]['id'],
        conditional_return_pins=inputs[6],
        saved_refinement_model_sha256=saved['source_hashes'][str(stage.MODELS.relative_to(ROOT))],
        current_model_sha256=sha(stage.MODELS),
        measured_reference='V(X2:7)-V(X2:4) = V(h_hot)-V(h_return)',
        cases=cases, refinement_fractional_change=changes,
        maximum_refinement_change_below_1_percent=max(changes.values()) < .01,
        interpretation='In this prescribed-drive stage, X2:4 moves substantially during flyback. Collector-to-ground and differential drive peaks are distinct and agree across 50/25 ns steps. The current horizontal-device model differs from the saved refinement deck, so this is a fresh conditional screen. The new flux and loss-shunt probes also agree across steps, but their values depend on the unverified graph, core dimensions, loss resistor, rectifier load and prescribed drive. Neither the pulse nor the core-loss result qualifies installed T3 turns or loss.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.ngspice)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(result['refinement_fractional_change'])
