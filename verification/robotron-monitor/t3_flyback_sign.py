"""Conditionally filter T3 polarity candidates by the source-visible flyback path."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import page4_t3_hv_compare as hv
import transformer_candidates as candidates

ROOT = Path(__file__).resolve().parent
READ = ROOT/'reference/k7222-11/t3-drive-polarity-source-read.json'
GRAPH = ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
PARAMETERS = ROOT/'reference/k7222-11/t3-initial-parameters.json'
TRANSCRIPTION = ROOT/'reference/k7222-11/horizontal-output-transcription.json'
SHEET = ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def component_pins(xml, wanted):
    root = ET.parse(xml).getroot()
    refs = {}
    for component in root.findall('./components/comp'):
        source_id = next((field.text for field in component.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id in wanted:
            if source_id in refs:
                raise ValueError('duplicate source component: '+source_id)
            refs[source_id] = component.get('ref')
    if set(refs) != set(wanted):
        raise ValueError('missing source components')
    by_ref = {reference: source_id for source_id, reference in refs.items()}
    pins = {source_id: {} for source_id in refs}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            source_id = by_ref.get(node.get('ref'))
            if source_id:
                pin = node.get('pin')
                if pin in pins[source_id]:
                    raise ValueError('duplicate component pin')
                pins[source_id][pin] = net.get('name').removeprefix('/')
    return pins


def source_checks(read, graph, transcription, xml):
    expected = {
        'drive_winding_endpoints': ['X2:7', 'X2:4'],
        'output_transistor_collector': {'part': 'V18', 'terminal': 'C', 't3_terminal': 'X2:7'},
        'damper': {'part': 'V17', 'anode_net': '0', 'cathode_terminal': 'X2:7'},
    }
    if read['source_edges'] != expected:
        raise ValueError('unexpected page-4 drive-path source read')
    drive = next(group['taps'] for group in graph['groups'] if group['id'] == 'drive')
    ports = transcription['ports']
    if (drive[0], drive[-1]) != ('X2_7', 'X2_4') or set(ports) != {
            tap for group in graph['groups'] for tap in group['taps']}:
        raise ValueError('candidate drive terminals differ from source')
    pins = component_pins(xml, {'012-6921:T3', '012-6921:V18', '012-6921:V17'})
    t3 = pins['012-6921:T3']
    v18 = pins['012-6921:V18']
    v17 = pins['012-6921:V17']
    collector = t3.get(str(ports.index('X2_7')+1))
    return dict(drive_pin_7_net=collector,
                drive_pin_4_net=t3.get(str(ports.index('X2_4')+1)),
                v18_pins=v18, v17_pins=v17,
                checks={
                    'collector_shares_drive_pin_7': collector is not None and v18.get('1') == collector,
                    'output_emitter_is_ground': v18.get('3') == '0',
                    'damper_anode_is_ground': v17.get('1') == '0',
                    'damper_cathode_shares_drive_pin_7': collector is not None and v17.get('2') == collector,
                    'drive_endpoints_distinct': collector is not None and t3.get(str(ports.index('X2_4')+1)) not in (None, collector),
                })


def isolated_pulse(graph, candidate, parameters, backend, directory):
    model, metadata = candidates.compile_model(graph, candidate, parameters, backend=backend)
    ports = metadata['ports']
    nodes = ['0' if port == 'X2_4' else port for port in ports]
    shunts = [f'Rref{index} {port} 0 1G' for index, port in enumerate(ports)
              if port not in ('X2_7', 'X2_4')]
    directory.mkdir()
    deck = directory/'pulse.cir'
    trace = directory/'trace.txt'
    deck.write_text('\n'.join([
        'T3 relative-polarity diagnostic; no full monitor claim', model,
        'Vdrive X2_7 0 PULSE(0 1 20n 1n 1n 100n 200n)', *shunts,
        'Xtest '+' '.join(nodes)+' T3_CANDIDATE',
        '.control', 'tran 1n 100n',
        f'wrdata {trace} v(X1_1,X1_16) v(X2_7)', 'quit', '.endc', '.end',
    ])+'\n')
    subprocess.run(['ngspice', '-b', str(deck)], check=True, capture_output=True, text=True)
    rows = [list(map(float, line.split())) for line in trace.read_text().splitlines()
            if line.strip()]
    if not rows or any(len(row) != 4 for row in rows):
        raise ValueError('incomplete isolated T3 pulse')
    row = min(rows, key=lambda item: abs(item[0]-80e-9))
    if not 79e-9 <= row[0] <= 81e-9 or row[3] < .99:
        raise ValueError('isolated drive pulse not present at sample')
    return row[1]


def compare(read, graph, parameters, transcription, xml, *, pdf_sha256, bench_dir):
    if read.get('format') != 'dac-monitor-t3-drive-polarity-source-read-v1':
        raise ValueError('unsupported T3 drive source read')
    if read['source_pdf_sha256'] != pdf_sha256 or len(read['source_views']) != 2:
        raise ValueError('wrong or incomplete page-4 source views')
    if any(view['file'] != 'older.pdf' or view['page'] != 4 for view in read['source_views']):
        raise ValueError('wrong page-4 source view')
    path = source_checks(read, graph, transcription, xml)
    hv_report = hv.compare(json.loads(hv.SOURCE.read_text()), transcription, graph, xml,
                           pdf_sha256=pdf_sha256)
    rows = []
    for candidate in candidates.enumerate_candidates(graph):
        solved = {backend: isolated_pulse(graph, candidate, parameters, backend,
                                          bench_dir/(candidate['id']+'-'+backend))
                  for backend in ('xspice', 'flux')}
        rows.append(dict(id=candidate['id'], high_voltage_relative_polarity=candidate['polarity']['high_voltage'],
                         xspice_hv_v_at_80ns=solved['xspice'], flux_hv_v_at_80ns=solved['flux'],
                         compatible=solved['xspice'] > .01 and solved['flux'] > .01))
    accepted = [row['id'] for row in rows if row['compatible']]
    backend_signs_agree = all((row['xspice_hv_v_at_80ns'] > .01) ==
                              (row['flux_hv_v_at_80ns'] > .01) for row in rows)
    passed = (all(path['checks'].values()) and hv_report['passed'] and backend_signs_agree
              and len(rows) == 16 and len(accepted) == 8
              and all(row['high_voltage_relative_polarity'] == -1 for row in rows if row['compatible']))
    return dict(format='dac-monitor-t3-flyback-sign-filter-v1',
                qualification='conditional polarity filter within the unverified T3 tap graph; not an A1/A5 closure or settled monitor result',
                source_read_sha256=sha(READ), source_pdf_sha256=pdf_sha256,
                hv_read_sha256=sha(hv.SOURCE), graph_sha256=sha(GRAPH),
                parameters_sha256=sha(PARAMETERS), sheet_sha256=sha(SHEET),
                source_edges=read['source_edges'], path_comparison=path,
                hv_source_comparison_passed=hv_report['passed'],
                pulse_setup='1 V positive pulse from X2:7 to X2:4; other T3 pins each shunted by 1 Gohm; V(X1:1)-V(X1:16) sampled near 80 ns',
                candidate_results=rows, backend_signs_agree=backend_signs_agree,
                accepted_candidate_ids=accepted, rejected_candidate_count=len(rows)-len(accepted),
                historical_polarity_verified=False, unresolved=read['unresolved'], passed=passed)


def run(source_pdf):
    read = json.loads(READ.read_text())
    if sha(source_pdf) != read['source_pdf_sha256']:
        raise ValueError('source PDF differs from T3 drive read')
    graph = json.loads(GRAPH.read_text())
    parameters = json.loads(PARAMETERS.read_text())
    transcription = json.loads(TRANSCRIPTION.read_text())
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        xml = root/'horizontal-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(SHEET)], check=True, capture_output=True, text=True)
        return compare(read, graph, parameters, transcription, xml,
                       pdf_sha256=sha(source_pdf), bench_dir=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{len(report['accepted_candidate_ids'])}/16 conditional polarity candidates remain")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
