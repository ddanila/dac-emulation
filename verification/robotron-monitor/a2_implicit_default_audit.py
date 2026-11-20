"""Inventory material implicit ngspice defaults in registered frame-path models.

This is an A2 gap inventory, not a model qualification or a claim that all
other ngspice parameters are immaterial. Internal subcircuit devices require
a separate audit.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parent
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
INVENTORY = ROOT/'reference/k7222-11/inventory.json'
# Parameters whose omitted built-in values can affect the A2 gain, switching,
# capacitance, breakdown, and temperature claims. Additional model parameters
# may matter too; this list is a first explicit-default screen.
CRITICAL = {
    'D': set('IS N RS CJO TT BV IBV VJ M FC EG XTI'.split()),
    'NPN': set('IS BF VAF RC RE CJE CJC TF TR IKF RB VJE MJE VJC MJC EG XTI FC'.split()),
    'PNP': set('IS BF VAF RC RE CJE CJC TF TR IKF RB VJE MJE VJC MJC EG XTI FC'.split()),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def declaration(path, name):
    source = re.sub(r'\n\s*\+\s*', ' ', Path(path).read_text())
    matches = re.findall(r'^\.model\s+'+re.escape(name)+r'\s+(D|NPN|PNP)\s*\(([^)]*)\)',
                         source, re.I | re.M)
    if len(matches) > 1:
        raise ValueError('duplicate discrete model declaration: '+name)
    if not matches:
        return None
    kind, body = matches[0]
    keys = re.findall(r'([A-Za-z][A-Za-z0-9_]*)\s*=', body)
    if len(keys) != len({key.upper() for key in keys}):
        raise ValueError('duplicate model parameter: '+name)
    return kind.upper(), {key.upper() for key in keys}


def run():
    register = json.loads(REGISTER.read_text())
    inventory = {part['id']: part for part in json.loads(INVENTORY.read_text())['parts']}
    rows = []
    model_hashes = {}
    for entry in register['families']+register['devices']:
        members = entry.get('member_ids', [entry['id']])
        kinds = {inventory[member]['kind'] for member in members}
        if not kinds <= {'bjt', 'diode', 'zener'}:
            continue
        if len(kinds) != 1:
            raise ValueError('mixed semiconductor kinds: '+entry['id'])
        filename = entry['model_file']
        path = ROOT/filename
        model_hashes[filename] = sha(path)
        found = declaration(path, entry['model'])
        if found is None:
            rows.append(dict(id=entry['id'], member_ids=members, kind=next(iter(kinds)),
                             model=entry['model'], model_file=filename,
                             status='no-discrete-declaration; inspect subcircuit/internal models'))
            continue
        model_type, explicit = found
        if model_type == 'D' and kinds not in ({'diode'}, {'zener'}):
            raise ValueError('diode model assigned to non-diode: '+entry['id'])
        if model_type in ('NPN', 'PNP') and kinds != {'bjt'}:
            raise ValueError('BJT model assigned to non-BJT: '+entry['id'])
        rows.append(dict(id=entry['id'], member_ids=members, kind=next(iter(kinds)),
                         model=entry['model'], model_file=filename, model_type=model_type,
                         explicit_parameters=sorted(explicit),
                         registered_parameters=sorted(entry['parameters']),
                         critical_implicit_defaults=sorted(CRITICAL[model_type]-explicit),
                         explicit_keys_without_same_named_register_field=
                         sorted(explicit-set(entry['parameters'])),
                         status='critical-defaults-open' if CRITICAL[model_type]-explicit
                         else 'critical-defaults-explicit; other qualification still required'))
    open_rows = [row for row in rows if row['status'] == 'critical-defaults-open']
    return dict(format='dac-monitor-a2-implicit-default-audit-v1',
                qualification='first critical-default inventory from declared model text; not an A2 completion check',
                ngspice_manual='https://ngspice.sourceforge.io/docs/ngspice-manual.pdf',
                register_sha256=sha(REGISTER), inventory_sha256=sha(INVENTORY),
                model_file_sha256=model_hashes,
                screened_parameters={kind: sorted(keys) for kind, keys in CRITICAL.items()},
                registered_semiconductor_entries=len(rows),
                entries_with_critical_defaults=len(open_rows),
                affected_instances=sum(len(row['member_ids']) for row in open_rows),
                rows=rows,
                remaining='Source-bound or explicitly examined behavior is needed for each listed default, including joint corners and connected stress. Same-name register comparison is diagnostic only: some entries use transformed parameter names. This screen does not cover internal subcircuit transistors or every ngspice optional parameter.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2)+'\n')
    print(f"{result['affected_instances']} frame-path instances have a screened implicit default")
