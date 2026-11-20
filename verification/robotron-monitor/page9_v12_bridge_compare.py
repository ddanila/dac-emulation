"""Compare the source-read page-9 V12 oscillator-to-ramp diode with KiCad.

This checks a local cross-sheet bridge and its direction, not the whole page.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page9-v12-source-read.json'
OSCILLATOR = ROOT/'circuits/k7222-11-vertical-oscillator.kicad_sch'
INTEGRATOR = ROOT/'circuits/k7222-11-vertical-integrator.kicad_sch'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pin_nets(xml, needed):
    root = ET.parse(xml).getroot()
    refs = {}
    ids = set()
    for component in root.findall('./components/comp'):
        source_ids = [p.get('value') for p in component.findall('property')
                      if p.get('name') == 'SourceId']
        if len(source_ids) != 1 or source_ids[0] in ids:
            raise ValueError('missing or duplicate exported SourceId')
        refs[component.get('ref')] = source_ids[0]
        ids.add(source_ids[0])
    if not needed <= ids:
        raise ValueError('scoped source part missing from export')
    pins = {part: {} for part in needed}
    for net in root.findall('./nets/net'):
        name = net.get('name').lstrip('/')
        for node in net.findall('node'):
            part = refs[node.get('ref')]
            if part not in pins:
                continue
            pin = node.get('pin')
            if pin in pins[part]:
                raise ValueError('exported terminal occurs on two nets')
            pins[part][pin] = name
    return pins


def compare(source, oscillator_xml, integrator_xml):
    if (source.get('format') != 'dac-monitor-page9-v12-source-read-v1'
            or source['source']['page'] != 9
            or source['scope']['board'] != '012-6931'
            or source['scope']['part'] != 'V12'
            or source['terminal_read']['left'] != 'cathode'
            or source['terminal_read']['right'] != 'anode'
            or set(source.get('v11_terminal_read', {})) !=
               {'collector', 'base', 'emitter', 'qualification'}):
        raise ValueError('source-side V12 direction is absent or changed')
    oscillator = pin_nets(oscillator_xml, {'012-6931:V11'})
    integrator = pin_nets(integrator_xml, {'012-6931:V12', '012-6931:A2'})
    v11 = oscillator['012-6931:V11']
    v12 = integrator['012-6931:V12']
    a2 = integrator['012-6931:A2']
    checks = {
        'v12_two_distinct_terminals': set(v12) == {'1', '2'} and
                                      len(set(v12.values())) == 2,
        'cathode_to_oscillator_pulse': v12.get('2') == 'vertical_pulse' and
                                       v11.get('1') == 'vertical_pulse',
        'anode_to_a2_positive_input': v12.get('1') == 'ramp_noninv' and
                                      a2.get('3') == 'ramp_noninv',
        'v11_base_and_emitter': v11.get('2') == 'vertical_base' and
                                v11.get('3') == '0',
    }
    return dict(format='dac-monitor-page9-v12-bridge-comparison-v1',
                qualification='local V11 collector/V12/A2 plus-input source bridge only; page-9 netlist and connected function remain open',
                source_read_sha256=sha(SOURCE),
                source_pdf_sha256=source['source']['pdf_sha256'],
                oscillator_sheet_sha256=sha(OSCILLATOR),
                integrator_sheet_sha256=sha(INTEGRATOR),
                exported_pin_nets={'V11': v11, 'V12': v12, 'A2_positive_input': a2.get('3')},
                checks=checks, passed=all(checks.values()))


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('schematic PDF differs from recorded source read')
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        exports = []
        for sheet in (OSCILLATOR, INTEGRATOR):
            xml = folder/(sheet.stem+'.xml')
            subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '--format',
                            'kicadxml', '-o', str(xml), str(sheet)],
                           check=True, capture_output=True, text=True)
            exports.append(xml)
        return compare(source, *exports)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print('page-9 V12 bridge:', 'match' if result['passed'] else 'mismatch')
    raise SystemExit(0 if result['passed'] else 2)
