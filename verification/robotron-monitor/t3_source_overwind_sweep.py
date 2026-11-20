"""Screen a source-informed CRT overwind in the loaded TP17 stage only."""
import argparse
import copy
import json
from pathlib import Path

import t3_output_stage_sweep as stage
import t3_tp17_path_sweep as tp17
import transformer_candidates


ROOT = Path(__file__).resolve().parent
PARAMETERS = ROOT/'reference/k7222-11/t3-coupled-source-overwind-parameters.json'
LEGACY_PARAMETERS = ROOT/'reference/k7222-11/t3-coupled-equivalent-parameters.json'
CASES = ((0.5, 100, True), (0.92, 100, True), (0.95, 100, True),
         (0.97, 100, True), (0.97, 50, True), (0.97, 100, False))


def run(ngspice):
    graph = json.loads(stage.GRAPH.read_text())
    parameters = json.loads(PARAMETERS.read_text())
    candidate = next(c for c in transformer_candidates.enumerate_candidates(graph)
                     if c['id'] == tp17.CANDIDATE_ID)
    transcription, parts, l3_r, l3_l = stage.source_parts()
    by_id = {part['source_id']: part for part in transcription['components']}
    parts += [by_id['012-6921:'+name] for name in tp17.SOURCE_PARTS]
    def screen(selected, step=100, probe=True):
        result = tp17.run_case(ngspice, graph, selected, candidate, parts,
                               l3_r, l3_l, 7.5, 0, backend='coupled',
                               max_step_ns=step, flux_probe=probe)
        measurement = result.get('result', {})
        result['stage_guideline_overlap'] = (
            result['status'] == 'complete' and
            64 <= measurement['sync_swing_v'] <= 96 and
            11000 <= measurement['eht_final_v'] <= 12000)
        return result

    cases = []
    for coupling, step, probe in CASES:
        selected = copy.deepcopy(parameters)
        selected['high_voltage_coupling']['value'] = coupling
        result = screen(selected, step, probe)
        result['primary_to_overwind_coupling'] = coupling
        cases.append(result)
    legacy = json.loads(LEGACY_PARAMETERS.read_text())
    factor_isolation = []
    for name, change in (('legacy', ()), ('resistance_only', ('resistance_ohm',)),
                         ('capacitance_only', ('capacitance_f',)),
                         ('coupling_only', ('coupling',)),
                         ('resistance_and_capacitance', ('resistance_ohm', 'capacitance_f'))):
        selected = copy.deepcopy(legacy)
        for key in change:
            if key == 'coupling':
                selected['high_voltage_coupling'] = copy.deepcopy(parameters['high_voltage_coupling'])
                selected['high_voltage_coupling']['value'] = 0.97
            else:
                selected['groups']['high_voltage'][0][key] = copy.deepcopy(
                    parameters['groups']['high_voltage'][0][key])
        outcome = screen(selected)
        outcome['factor_case'] = name
        outcome['primary_to_overwind_coupling'] = 0.97 if 'coupling' in change else 0.999
        factor_isolation.append(outcome)
    return {
        'format': 'dac-monitor-t3-source-overwind-sweep-v1',
        'qualification': 'conditional class-typical overwind screen on a prescribed-drive 4–5 ms stage; not original K7222.11 winding data, a converged connected monitor, or an A5 freeze',
        'source_hashes': {str(path.relative_to(ROOT)): tp17.sha256(path)
                          for path in (PARAMETERS, LEGACY_PARAMETERS, stage.GRAPH, stage.TRANSCRIPTION,
                                       stage.MODELS,
                                       ROOT/'reference/k7222-11/t3-hv-winding-comparator.json',
                                       ROOT/'reference/k7222-11/design-point.json',
                                       ROOT/'magnetics.py', ROOT/'transformer_candidates.py',
                                       ROOT/'t3_output_stage_sweep.py',
                                       ROOT/'t3_tp17_path_sweep.py',
                                       ROOT/'t3_source_overwind_sweep.py')},
        'ngspice_sha256': tp17.sha256(ngspice),
        'candidate_id': tp17.CANDIDATE_ID,
        'model': '14 individually wound sections; 0.999 coupling except each HV-overwind pair, which uses the selected class-typical k; prior series leakage remains separately provisional',
        'source_limits': parameters['source_basis'],
        'manual_tp17_guideline_range_vpp': [64, 96],
        'manual_eht_range_v': [11000, 12000],
        'cases': cases,
        'factor_isolation': factor_isolation,
        'remaining': ['Qualify original .11 T3 graph, section parasitics and core',
                      'Resolve numerical sensitivity before any connected native-grid score'],
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ngspice', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(run(args.ngspice), indent=2)+'\n')
