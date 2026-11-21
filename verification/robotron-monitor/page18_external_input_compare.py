"""Check the page-18 X9 input against the assembled logical cable seam."""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET

import steady_supply
import transformer_candidates
from page18_vertical_cable_compare import physical_pins


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reference/k7222-11/page18-interconnect-transcription.json'
ASSEMBLY = ROOT / 'reference/k7222-11/assembly.json'
OUTPUT = ROOT / 'reference/k7222-11/page18-external-input-comparison.json'
SOURCE_PDF = ROOT.parents[1] / 'build/monitor/phase-a/sources/older.pdf'
SIGNALS = {'1': ('VIDEO', 'video'), '3': ('BSYN', 'bsyn'),
           '5': ('INTENS', 'intens')}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, assembly_source, deck, input_export, *, source_pdf_sha256):
    if source['source']['page'] != 18 or source['source']['pdf_sha256'] != source_pdf_sha256:
        raise ValueError('page-18 independent read differs from source PDF')
    pins = source['connectors']['012-6921:X9']
    if set(pins) != {'1', '3', '4', '5', '6'}:
        raise ValueError('unexpected source X9 pin inventory')
    declared = assembly_source['external_input']
    if (declared['board'], declared['connector']) != ('012-6921', 'X9'):
        raise ValueError('assembly external input is not X9')
    expected = {pin: ('0' if label == '00' else label) for pin, label in pins.items()}
    if declared['pins'] != expected or pins['4'] != '00' or pins['6'] != '00':
        raise ValueError('external input declaration differs from page 18')
    lines = {tokens[0]: tokens for line in deck.splitlines()
             if (tokens := line.split()) and tokens[0][0] in 'CRXV'}
    if lines.get('Rreturn', [])[:3] != ['Rreturn', 'computer_return', '0']:
        raise ValueError('input cable lacks a return to monitor ground')
    if lines.get('X201', [])[-1:] != ['T200_BOUND']:
        raise ValueError('input receiver is not the bounded T200 stage')
    rows = []
    for pin, (label, signal) in SIGNALS.items():
        if pins[pin] != label:
            raise ValueError(f'X9:{pin} label changed')
        source_name = f'Vlogic_{signal}'
        driver_name = f'X10{list(SIGNALS).index(pin) + 1}'
        if lines.get(source_name, [])[:3] != [source_name, f'logic_{signal}', 'computer_return']:
            raise ValueError(f'missing {signal} logic source')
        if lines.get(driver_name, [])[:5] != [driver_name, f'logic_{signal}',
                                               f'tx_{signal}', 'computer_return', 'S37_DRIVER']:
            raise ValueError(f'missing {signal} cable driver')
        last = f'tx_{signal}'
        for section in range(4):
            node = f'rx_{signal}' if section == 3 else f'cable_{signal}_{section}'
            if lines.get(f'Rwire_{signal}_{section}', [])[:3] != [
                    f'Rwire_{signal}_{section}', last, node]:
                raise ValueError(f'X9:{pin} cable section {section} disconnected')
            if lines.get(f'Cwire_{signal}_{section}', [])[:3] != [
                    f'Cwire_{signal}_{section}', node, '0']:
                raise ValueError(f'X9:{pin} cable shunt {section} disconnected')
            last = node
        if f'rx_{signal}' not in lines.get('X201', []):
            raise ValueError(f'X9:{pin} receiver input disconnected')
        rows.append(dict(pin=pin, source_signal=label, model_receive_node=last,
                         driver=driver_name, cable_sections=4, receiver='X201'))
    root = ET.parse(input_export).getroot()
    x9_count = sum(
        any(field.get('name') == 'SourceId' and field.text == '012-6921:X9'
            for field in comp.findall('./fields/field'))
        for comp in root.findall('./components/comp'))
    if x9_count > 1:
        raise ValueError('duplicate physical X9 connector')
    physical_x9_present = x9_count == 1
    if not physical_x9_present:
        raise ValueError('missing physical X9 connector')
    actual_pins = physical_pins(input_export, '012-6921:X9')
    model_pins = {pin: ('0' if label == '00' else
                        f'rx_{SIGNALS[pin][1]}') for pin, label in pins.items()}
    if actual_pins != model_pins:
        raise ValueError('physical X9 pin nets differ from page-18 input seam')
    return dict(format='dac-monitor-page18-external-input-comparison-v1',
                qualification='source X9 labels, physical input connector and assembled logical receiver/cable continuity checked; full page-18 function review remains open',
                source_sha256=sha(SOURCE), source_pdf_sha256=source_pdf_sha256,
                assembly_sha256=sha(ASSEMBLY),
                input_sheet_sha256=sha(ROOT / 'circuits/k7222-11-input.kicad_sch'),
                steady_supply_sha256=sha(ROOT / 'steady_supply.py'),
                checker_sha256=sha(Path(__file__)),
                input_connector='012-6921:X9', signal_rows=rows,
                return_pins=['4', '6'], return_element='Rreturn',
                physical_x9_present=physical_x9_present,
                physical_pins_checked=len(actual_pins),
                logical_seam_passed=True,
                remaining=['X9 cable and driver stay an equivalent outside the audit-only connector',
                           'page-3/4 input and contrast function remains unqualified'])


def run(source_pdf=SOURCE_PDF):
    source = json.loads(SOURCE.read_text())
    assembly_source = json.loads(ASSEMBLY.read_text())
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / 'assembly'
        assembly = steady_supply.assemble(output)
        selection = {'status': 'complete', 'period_ticks': 3600000,
                     'clock_hz': 179712000,
                     'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
        candidate = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])[0]
        deck, _ = steady_supply.deck(assembly, selection, candidate)
        return compare(source, assembly_source, deck, output / 'k7222-11-input.xml',
                       source_pdf_sha256=sha(source_pdf))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, default=SOURCE_PDF)
    parser.add_argument('--output', type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f"{len(report['signal_rows'])} X9 signals and 2 returns checked; "
          f"physical connector present: {report['physical_x9_present']}")
