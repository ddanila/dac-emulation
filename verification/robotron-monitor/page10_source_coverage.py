"""Inventory page-10 model parts touched by passed scoped source reads."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
REF = ROOT / 'reference/k7222-11'
SHEET = ROOT / 'circuits/k7222-11-vertical-output.kicad_sch'
REPORT = REF / 'page10-model-source-coverage.json'
READS = (
    ('page10-a3-source-netlist.json', 'page10-a3-comparison.json'),
    ('page10-a3-bias-source-netlist.json', 'page10-a3-bias-comparison.json'),
    ('page10-feedback-source-netlist.json', 'page10-feedback-comparison.json'),
    ('page10-output-pair-source-netlist.json', 'page10-output-pair-comparison.json'),
    ('page10-symmetry-input-source-read.json', 'page10-symmetry-input-comparison.json'),
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit():
    source_ids = re.findall(r'\(property "SourceId" "012-6931:([^\"]+)"',
                            SHEET.read_text())
    if len(source_ids) != len(set(source_ids)):
        raise ValueError('duplicate page-10 SourceId')
    modeled = set(source_ids)
    if 'X2' not in modeled:
        raise ValueError('physical X2 source connector absent')
    touched = set()
    receipts = []
    for read_name, comparison_name in READS:
        source_path, comparison_path = REF / read_name, REF / comparison_name
        source = json.loads(source_path.read_text())
        comparison = json.loads(comparison_path.read_text())
        source_hash_key = ('source_read_sha256' if 'source_read_sha256' in comparison
                           else 'source_netlist_sha256')
        if comparison.get(source_hash_key) != sha(source_path):
            raise ValueError('source receipt hash stale: ' + comparison_name)
        if comparison.get('sheet_sha256') != sha(SHEET):
            raise ValueError('sheet receipt hash stale: ' + comparison_name)
        if comparison.get('passed') is not True:
            raise ValueError('source comparison failed: ' + comparison_name)
        local = {terminal.split(':', 1)[0]
                 for terminals in source['nets'].values()
                 for terminal in terminals}
        if not local or not local <= modeled:
            raise ValueError('source read names parts outside current sheet: ' + read_name)
        scope = source['scope']
        scope_parts = ({part.split(':', 1)[1] for part in scope}
                       if isinstance(scope, list) else set(scope['parts']))
        if not local <= scope_parts:
            raise ValueError('source terminal outside declared scope: ' + read_name)
        touched |= local
        receipts.append({'source_read': read_name, 'comparison': comparison_name,
                         'parts_touched': sorted(local), 'terminal_mentions': sum(
                             len(terminals) for terminals in source['nets'].values())})
    functional = modeled - {'X2'}
    no_terminal = sorted(functional - touched)
    return {
        'format': 'dac-monitor-page10-model-source-coverage-v1',
        'qualification': 'Current modeled-part touch census from five passed scoped reads; does not establish complete source-page inventory, all pins or page-edge joins',
        'sheet_sha256': sha(SHEET), 'modeled_functional_parts': len(functional),
        'functional_parts_with_scoped_source_terminal': len(functional & touched),
        'functional_parts_without_scoped_source_terminal': len(no_terminal),
        'without_source_terminal': no_terminal,
        'physical_x2_connector_touched': 'X2' in touched,
        'receipts': receipts,
        'open': ['Nine modeled parts still have no source terminal in the passed scoped reads.',
                 'Part touch does not prove all terminals or all source-page parts have been inventoried.',
                 'C23 schematic/manual topology conflict and page-edge joins remain separate A1 issues.'],
    }


if __name__ == '__main__':
    result = audit()
    REPORT.write_text(json.dumps(result, indent=2) + '\n')
    print(f"page 10: {result['functional_parts_with_scoped_source_terminal']}/"
          f"{result['modeled_functional_parts']} functional parts touched")
