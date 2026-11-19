"""Check the source-read T3 high-voltage path against a fresh KiCad export."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/t3-hv-terminal-read.json'
TRANSCRIPTION = ROOT/'reference/k7222-11/horizontal-output-transcription.json'
GRAPH = ROOT/'reference/k7222-11/t3-winding-hypothesis.json'
SHEET = ROOT/'circuits/k7222-11-horizontal-output.kicad_sch'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def component_pins(xml):
    root = ET.parse(xml).getroot()
    refs = {}
    for comp in root.findall('./components/comp'):
        source_id = next((field.text for field in comp.findall('./fields/field')
                          if field.get('name') == 'SourceId'), None)
        if source_id in ('012-6921:T3', '012-6921:V21'):
            if source_id in refs:
                raise ValueError('duplicate T3/V21 source component')
            refs[source_id] = comp.get('ref')
    if set(refs) != {'012-6921:T3', '012-6921:V21'}:
        raise ValueError('missing T3/V21 source component')
    pins = {source_id: {} for source_id in refs}
    by_ref = {ref: source_id for source_id, ref in refs.items()}
    for net in root.findall('./nets/net'):
        for node in net.findall('node'):
            source_id = by_ref.get(node.get('ref'))
            if source_id:
                pin = node.get('pin')
                if pin in pins[source_id]:
                    raise ValueError('T3/V21 pin occurs twice')
                pins[source_id][pin] = net.get('name').removeprefix('/')
    return pins


def compare(source, transcription, graph, xml, *, pdf_sha256):
    if source.get('format') != 'dac-monitor-t3-hv-terminal-read-v1':
        raise ValueError('unsupported T3 source reading')
    views = [view for view in source['source_views'] if view['file'] == 'older.pdf']
    if len(views) != 2 or any(view['page'] != 4 or view['pdf_sha256'] != pdf_sha256
                              for view in views):
        raise ValueError('wrong or incomplete page-4 source views')
    edges = {edge['kind']: edge for edge in source['source_edges']}
    if len(edges) != 3 or set(edges) != {'winding', 'rectifier', 'output'}:
        raise ValueError('incomplete high-voltage source edges')
    winding, diode, output = edges['winding'], edges['rectifier'], edges['output']
    if diode['part'] != 'V21' or output['terminal'] != diode['cathode']:
        raise ValueError('source high-voltage output does not follow rectifier')
    if diode['anode'] not in winding['terminals'] or len(winding['terminals']) != 2:
        raise ValueError('source rectifier anode is not on the HV winding')
    if output['net'] != 'EHT/UG3':
        raise ValueError('unmapped high-voltage source output')
    eht_net = 'eht'
    if transcription['source'] != {'file': 'older.pdf', 'page': 4}:
        raise ValueError('wrong model transcription source')
    ports = transcription['ports']
    graph_ports = [tap for group in graph['groups'] for tap in group['taps']]
    if len(ports) != len(set(ports)) or len(ports) != len(graph_ports) or set(ports) != set(graph_ports):
        raise ValueError('T3 wrapper ports differ from winding hypothesis')
    hv_group = next((group['taps'] for group in graph['groups']
                     if group['id'] == 'high_voltage'), None)
    if hv_group is None or set(hv_group) != {name.replace(':', '_') for name in winding['terminals']}:
        raise ValueError('model HV winding terminals differ from source')
    if output['terminal'].replace(':', '_') in ports:
        raise ValueError('rectified EHT output appears as a magnetic port')
    pins = component_pins(xml)
    t3 = {port: pins['012-6921:T3'].get(str(index))
          for index, port in enumerate(ports, start=1)}
    rectifier = pins['012-6921:V21']
    actual = {
        'anode_shares_winding_pin': rectifier.get('1') == t3[diode['anode'].replace(':', '_')],
        'cathode_is_eht': rectifier.get('2') == eht_net,
        'anode_and_cathode_distinct': rectifier.get('1') != rectifier.get('2'),
        'both_hv_winding_pins_connected': all(t3[name.replace(':', '_')] is not None
                                              for name in winding['terminals']),
        'hv_winding_pins_distinct': len({t3[name.replace(':', '_')]
                                         for name in winding['terminals']}) == 2,
        'magnetic_pins_complete': len(pins['012-6921:T3']) == len(ports),
        'rectifier_pins_complete': set(rectifier) == {'1', '2'},
    }
    return dict(format='dac-monitor-page4-t3-hv-comparison-v1',
                qualification='three settled HV source edges checked; T3 return, other taps and polarity remain open',
                source_sha256=sha(SOURCE), source_pdf_sha256=pdf_sha256,
                transcription_sha256=sha(TRANSCRIPTION), graph_sha256=sha(GRAPH),
                sheet_sha256=sha(SHEET), source_edges=source['source_edges'],
                model_hv_pins={name: t3[name.replace(':', '_')] for name in winding['terminals']},
                model_v21_pins=rectifier, model_eht_net=eht_net, checks=actual,
                unresolved=source['unresolved'], passed=all(actual.values()))


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source_views'][0]['pdf_sha256']:
        raise ValueError('source PDF differs from recorded page-4 reading')
    with tempfile.TemporaryDirectory() as directory:
        xml = Path(directory)/'horizontal-output.xml'
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format', 'kicadxml',
                        '-o', str(xml), str(SHEET)], check=True, capture_output=True, text=True)
        return compare(source, json.loads(TRANSCRIPTION.read_text()),
                       json.loads(GRAPH.read_text()), xml, pdf_sha256=sha(source_pdf))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{sum(report['checks'].values())}/{len(report['checks'])} HV-path checks pass")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
