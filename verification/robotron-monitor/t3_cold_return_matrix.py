"""Compare conditional T3 HV cold-end and upper-tap returns under one load."""
import argparse
import json
from pathlib import Path
import subprocess
import tempfile

import t3_flyback_sign
import t3_return_variants as returns
import transformer_candidates

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT/'reference/k7222-11/t3-cold-return-matrix.json'


def run(source_pdf):
    read = json.loads(returns.READ.read_text())
    if returns.sha(source_pdf) != read['source_pdf_sha256']:
        raise ValueError('page-4 PDF differs from the existing T3 source read')
    graph = json.loads(returns.GRAPH.read_text())
    parameters = json.loads(returns.PARAMETERS.read_text())
    sign = json.loads(returns.SIGN.read_text())
    transcription = json.loads(returns.TRANSCRIPTION.read_text())
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(returns.SHEET)], check=True,
                       capture_output=True, text=True)
        pins = t3_flyback_sign.component_pins(xml, {'012-6921:T3'})['012-6921:T3']
    model_nodes = {port: pins.get(str(index))
                   for index, port in enumerate(transcription['ports'], 1)}
    model_checks = {
        'upper_return_currently_tied': model_nodes['X1_3'] == model_nodes['X2_3'] == 'h_upper2',
        'hv_cold_currently_floating_shared': model_nodes['X1_7'] == model_nodes['X1_16'] == 'h_hvcold',
        'all_t3_ports_present': len(pins) == len(transcription['ports']),
    }
    accepted = set(sign['accepted_candidate_ids'])
    candidates = [candidate for candidate in transformer_candidates.enumerate_candidates(graph)
                  if candidate['id'] in accepted]
    if len(candidates) != 8 or any(candidate['polarity']['high_voltage'] != -1
                                   for candidate in candidates):
        raise ValueError('stored sign-compatible candidate set differs from current graph')
    rows = []
    for candidate in candidates:
        results = {}
        for joined in (True, False):
            for cold_mode in ('shared_floating', 'shared_grounded', 'hv_only_grounded'):
                key = f"{'tied' if joined else 'open'}__{cold_mode}"
                results[key] = returns.simulate(graph, parameters, candidate, joined,
                                                'flux', cold_mode=cold_mode)
        rows.append({'candidate_id': candidate['id'], 'polarity': candidate['polarity'],
                     'results': results})
    complete = all(result['status'] == 'complete'
                   for row in rows for result in row['results'].values())
    conditional_discriminator = complete and all(
        row['results']['open__shared_floating']['eht_peak_v'] < .01
        and row['results']['open__shared_grounded']['eht_peak_v'] > 10
        and row['results']['open__hv_only_grounded']['eht_peak_v'] > 10
        and row['results']['tied__shared_floating']['eht_peak_v'] > 10
        for row in rows)
    return {
        'format': 'dac-monitor-t3-cold-return-matrix-v1',
        'qualification': 'isolated, conditional topology sensitivity; does not establish the K7222.11 factory return or predict connected EHT',
        'source_pdf_sha256': returns.sha(source_pdf),
        'source_read_sha256': returns.sha(returns.READ),
        'graph_sha256': returns.sha(returns.GRAPH),
        'parameters_sha256': returns.sha(returns.PARAMETERS),
        'sign_filter_sha256': returns.sha(returns.SIGN),
        'sheet_sha256': returns.sha(returns.SHEET),
        'transcription_sha256': returns.sha(returns.TRANSCRIPTION),
        'model_nodes': {port: model_nodes[port]
                        for port in ('X2_3', 'X1_3', 'X1_7', 'X1_16')},
        'model_checks': model_checks,
        'external_comparators': [
            {'url': 'https://www.robotrontechnik.de/html/forum/thwb/showtopic.php?threadid=6955',
             'post': '006, 6 March 2011',
             'observation': 'A repair discussion calls the original K7222 HV coil footpoint grounded; monitor revision is not identified.',
             'tier': 'firsthand repair comparator, not .11 pin evidence'},
            {'url': 'https://www.robotrontechnik.de/html/forum/thwb/showtopic.php?threadid=3903',
             'post': '016, 5 January 2009',
             'observation': 'A repairer inspecting a K7222 board reports three secondary-coil leads to the primary, with other secondary pins floating; exact .11 routing is not given.',
             'tier': 'firsthand board comparator, not .11 pin evidence'},
        ],
        'variants': [
            {'cold_mode': 'shared_floating', 'X1_16': 'hvcold', 'X1_7': 'hvcold',
             'interpretation': 'current KiCad HV cold hypothesis'},
            {'cold_mode': 'shared_grounded', 'X1_16': '0', 'X1_7': '0',
             'interpretation': 'both currently shared terminals grounded'},
            {'cold_mode': 'hv_only_grounded', 'X1_16': '0', 'X1_7': 'hvcold',
             'interpretation': 'HV cold grounded, upper-tap cold remains separate'},
        ],
        'pulse_setup': '1 V positive 16 us primary pulse every 62.5 us, five pulses; isolated V21-class diode, 1 nF EHT capacitance, 200 Mohm leakage and 1 Gohm auxiliary shunts; flux backend',
        'candidate_results': rows,
        'interpretation': 'The earlier open X1:3/X2:3 near-zero EHT is specific to the floating HV cold hypothesis. Grounding X1:16 yields a charging path even when X1:3 remains open. These results do not select either physical return: the source scan and connected stage still need review.',
        'passed': all(model_checks.values()) and conditional_discriminator,
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['candidate_results'])} candidates, {len(report['variants']) * 2} return variants; passed={report['passed']}")
    if not report['passed']:
        raise SystemExit(1)
