"""Conditionally prune T3 auxiliary polarity by V14's negative-G1 function."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import t3_flyback_sign as hv_sign
import transformer_candidates as candidates

ROOT = Path(__file__).resolve().parent
READ = ROOT/'reference/k7222-11/t3-g1-rectifier-source-read.json'
HV_FILTER = ROOT/'reference/k7222-11/t3-flyback-sign-filter.json'
GRAPH = ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
PARAMETERS = ROOT/'reference/k7222-11/t3-initial-parameters.json'
TRANSCRIPTION = ROOT/'reference/k7222-11/horizontal-output-transcription.json'
TARGETS = ROOT/'reference/k7222-11/service-observations.json'
SHEET = ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def check_path(read, transcription, targets, xml):
    edges = read['source_edges']
    if edges != dict(v14_anode_net='h_g1raw', v14_cathode_t3_terminal='X2:6',
                     c18_other_terminal='00', manual_tp17_terminal='V14:K'):
        raise ValueError('page-4 V14 source edges changed')
    ports = transcription['ports']
    if transcription['port_nets']['X2_6'] != 'h_sync' or transcription['port_nets']['X2_5'] != '0':
        raise ValueError('T3 auxiliary port mapping changed')
    point = next(row for row in targets['waveforms'] if row['test_point'] == 17)
    if point['node'] != '012-6921:V14:K' or point['model_node'] != 'h_sync':
        raise ValueError('manual TP17 mapping changed')
    pins = hv_sign.component_pins(xml, {'012-6921:T3', '012-6921:V14', '012-6921:C18'})
    t3, v14, c18 = (pins[key] for key in ('012-6921:T3', '012-6921:V14', '012-6921:C18'))
    aux_hot = t3.get(str(ports.index('X2_6')+1))
    aux_cold = t3.get(str(ports.index('X2_5')+1))
    checks = dict(v14_cathode_at_x2_6=aux_hot is not None and v14.get('2') == aux_hot,
                  v14_anode_at_c18=v14.get('1') is not None and v14.get('1') == c18.get('1'),
                  c18_other_end_at_zero=c18.get('2') == '0',
                  auxiliary_cold_at_zero_in_current_assembly=aux_cold == '0')
    return dict(v14_pins=v14, c18_pins=c18, x2_5_net=aux_cold,
                x2_6_net=aux_hot, checks=checks)


def isolated_aux_pulse(graph, candidate, parameters, backend, directory):
    model, metadata = candidates.compile_model(graph, candidate, parameters, backend=backend)
    ports = metadata['ports']
    nodes = ['0' if port == 'X2_4' else port for port in ports]
    shunts = [f'Rref{index} {port} 0 1G' for index, port in enumerate(ports)
              if port not in ('X2_7', 'X2_4')]
    directory.mkdir()
    deck, trace = directory/'pulse.cir', directory/'trace.txt'
    deck.write_text('\n'.join([
        'T3 G1 auxiliary relative-polarity diagnostic', model,
        'Vdrive X2_7 0 PULSE(0 1 20n 1n 1n 100n 200n)', *shunts,
        'Xtest '+' '.join(nodes)+' T3_CANDIDATE',
        '.control', 'tran 1n 100n',
        f'wrdata {trace} v(X2_6,X2_5) v(X2_7)', 'quit', '.endc', '.end',
    ])+'\n')
    result = subprocess.run(['ngspice', '-b', str(deck)],
                            check=True, capture_output=True, text=True)
    if 'Error:' in result.stdout + result.stderr:
        raise ValueError('ngspice error')
    rows = [list(map(float, line.split())) for line in trace.read_text().splitlines()
            if line.strip()]
    if not rows or any(len(row) != 4 for row in rows):
        raise ValueError('incomplete T3 auxiliary trace')
    sample = min(rows, key=lambda row: abs(row[0]-80e-9))
    if not 79e-9 <= sample[0] <= 81e-9 or sample[3] < .99:
        raise ValueError('isolated flyback pulse absent at sample')
    return sample[1]


def run(source_pdf, cross_revision_pdf):
    read = json.loads(READ.read_text())
    if (read['format'] != 'dac-monitor-t3-g1-rectifier-source-read-v1'
            or sha(source_pdf) != read['source_pdf_sha256']
            or sha(cross_revision_pdf) != read['cross_revision']['pdf_sha256']
            or len(read['source_views']) != 2):
        raise ValueError('V14 source provenance changed')
    graph = json.loads(GRAPH.read_text())
    parameters = json.loads(PARAMETERS.read_text())
    transcription = json.loads(TRANSCRIPTION.read_text())
    targets = json.loads(TARGETS.read_text())
    hv_filter = json.loads(HV_FILTER.read_text())
    if hv_filter['graph_sha256'] != sha(GRAPH) or hv_filter['parameters_sha256'] != sha(PARAMETERS):
        raise ValueError('earlier HV sign filter is stale')
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        xml = root/'horizontal-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(SHEET)],
                       check=True, capture_output=True, text=True)
        path = check_path(read, transcription, targets, xml)
        accepted = set(hv_filter['accepted_candidate_ids'])
        rows = []
        for candidate in candidates.enumerate_candidates(graph):
            if candidate['id'] not in accepted:
                continue
            solved = {backend: isolated_aux_pulse(graph, candidate, parameters,
                                                   backend, root/(candidate['id']+'-'+backend))
                      for backend in ('xspice', 'flux')}
            rows.append(dict(id=candidate['id'], polarity=candidate['polarity'],
                             xspice_aux_v_at_80ns=solved['xspice'],
                             flux_aux_v_at_80ns=solved['flux'],
                             compatible=solved['xspice'] < -.01 and solved['flux'] < -.01))
    retained = [row['id'] for row in rows if row['compatible']]
    passed = (all(path['checks'].values()) and len(rows) == 8 and len(retained) == 4
              and all(row['polarity']['auxiliary'] == 1 for row in rows if row['compatible'])
              and all((row['xspice_aux_v_at_80ns'] < -.01) ==
                      (row['flux_aux_v_at_80ns'] < -.01) for row in rows))
    return dict(format='dac-monitor-t3-g1-polarity-filter-v1',
                qualification='conditional function/sign filter within an unverified auxiliary winding and X2:5 return; no A1/A5 graph closure or TP17 amplitude claim',
                source_read_sha256=sha(READ), source_pdf_sha256=sha(source_pdf),
                cross_revision_pdf_sha256=sha(cross_revision_pdf),
                graph_sha256=sha(GRAPH), parameters_sha256=sha(PARAMETERS),
                transcription_sha256=sha(TRANSCRIPTION), targets_sha256=sha(TARGETS),
                sheet_sha256=sha(SHEET), previous_hv_filter_sha256=sha(HV_FILTER),
                source_edges=read['source_edges'], path_comparison=path,
                functional_rule=read['functional_inference'],
                pulse_setup='1 V positive pulse across X2:7-to-X2:4; other ports have 1 Gohm shunts; V(X2:6)-V(X2:5) sampled near 80 ns in xspice and flux backends',
                candidate_results=rows, accepted_candidate_ids=retained,
                rejected_candidate_count=len(rows)-len(retained),
                historical_polarity_verified=False, unresolved=read['unresolved'],
                passed=passed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--cross-revision-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf, args.cross_revision_pdf)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{len(report['accepted_candidate_ids'])}/8 G1-function candidates remain")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
