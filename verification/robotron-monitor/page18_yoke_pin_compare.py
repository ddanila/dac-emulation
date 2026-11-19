"""Compare the page-18 yoke connector and winding endpoints with the model."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from page18_vertical_cable_compare import physical_pins
import steady_supply
import transformer_candidates

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT/'reference/k7222-11/page18-interconnect-transcription.json'
SHEET = ROOT/'circuits/k7222-11-vertical-output.kicad_sch'
CONNECTOR = '012-6931:X2'
MODEL_NETS = {'41P': 'p41', 'X1': 'hy1', 'X2': 'hy2', 'Y1': 'y1', 'Y2': 'y2'}
YOKE_PINS = {'1', '3', '4', '6'}
WINDING_NODES = {
    'Rhorizontal': ('hy1', 'h_winding'),
    'Lhorizontal': ('h_winding', 'hy2'),
    'Rvertical': ('y1', 'v_winding'),
    'Lvertical': ('v_winding', 'y2'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare(source, export, deck, *, pdf_sha256):
    if source.get('format') != 'dac-monitor-interconnect-source-v1':
        raise ValueError('unsupported page-18 source transcription')
    if source['source']['page'] != 18 or source['source']['pdf_sha256'] != pdf_sha256:
        raise ValueError('wrong scanned page-18 source')
    board = source['connectors'][CONNECTOR]
    yoke = source['connectors']['yoke']
    if set(board) != {str(pin) for pin in range(1, 7)} or set(yoke) != YOKE_PINS:
        raise ValueError('incomplete page-18 yoke or board connector source pins')
    if [board[str(pin)] for pin in range(1, 7)] != ['41P', '41P', 'Y1', 'Y2', 'X2', 'X1']:
        raise ValueError('unexpected source board connector order')
    if len(set(yoke.values())) != 4 or set(yoke.values()) != {'X1', 'X2', 'Y1', 'Y2'}:
        raise ValueError('incomplete source yoke winding labels')
    actual = physical_pins(export, CONNECTOR)
    board_rows = [dict(pin=pin, source_signal=label, expected_model_net=MODEL_NETS[label],
                       export_net=actual.get(pin)) for pin, label in board.items()]
    yoke_rows = [dict(yoke_pin=pin, board_pin=next(bp for bp, name in board.items() if name == label),
                      source_signal=label, model_net=MODEL_NETS[label])
                 for pin, label in yoke.items()]
    lines = [line.split() for line in deck.splitlines() if line.split() and line.split()[0] in WINDING_NODES]
    if len(lines) != 4 or {line[0] for line in lines} != set(WINDING_NODES):
        raise ValueError('missing or duplicate assembled yoke winding element')
    winding_rows = [dict(element=line[0], expected_nodes=list(WINDING_NODES[line[0]]),
                         actual_nodes=line[1:3], parameter=line[3] if len(line) == 4 else None)
                    for line in lines]
    missing = [row for row in board_rows if row['export_net'] != row['expected_model_net']]
    extra = sorted(set(actual) - set(board))
    winding_misses = [row for row in winding_rows if row['actual_nodes'] != row['expected_nodes']
                      or row['parameter'] != '{yoke_'+('horizontal' if 'horizontal' in row['element'] else 'vertical')+
                                              ('_r}' if row['element'].startswith('R') else '_l}')]
    return dict(format='dac-monitor-page18-yoke-pin-comparison-v1',
                qualification='six vertical-board connector pins and four yoke labels checked; external winding nodes checked in assembled deck',
                source_sha256=sha(SOURCE), source_pdf_sha256=pdf_sha256,
                sheet_sha256=sha(SHEET),
                board_connector_pins_checked=6, yoke_terminals_checked=4,
                board_connector=board_rows, yoke_terminals=yoke_rows,
                winding_elements=winding_rows, pin_misses=missing,
                extra_kicad_connector_pins=extra, winding_misses=winding_misses,
                open_checks=['panel controls need source-to-KiCad pin comparison',
                             'the horizontal-yoke pass-through is audit-only on the vertical board',
                             'yoke R/L and field strength remain bounded hypotheses',
                             'T3 internal winding topology is outside page 18'],
                passed=not (missing or extra or winding_misses))


def run(source_pdf):
    source = json.loads(SOURCE.read_text())
    if sha(source_pdf) != source['source']['pdf_sha256']:
        raise ValueError('source PDF differs from recorded page-18 reading')
    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory)/'assembly'
        assembly = steady_supply.assemble(output)
        selection = {'status': 'complete', 'period_ticks': 3600000,
                     'clock_hz': 179712000, 'events': [[0, 0, 1, 1], [1800000, 1, 0, 1]]}
        candidate = transformer_candidates.enumerate_candidates(assembly['magnetic_graph'])[0]
        deck, _ = steady_supply.deck(assembly, selection, candidate)
        return compare(source, output/'k7222-11-vertical-output.xml', deck,
                       pdf_sha256=sha(source_pdf))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-pdf', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args.source_pdf)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{6-len(report['pin_misses'])}/6 board pins; "
          f"{4-len(report['winding_misses'])}/4 winding elements")
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
