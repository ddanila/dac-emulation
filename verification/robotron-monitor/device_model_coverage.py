"""Inventory every A2 frame-path device against the assembled model register.

An active SPICE model name is not evidence of sourced parameters. This report
keeps assembly presence and A2 register coverage separate.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import tempfile

import phase_a_review
import steady_supply

ROOT = Path(__file__).resolve().parent
INVENTORY = ROOT/'reference/k7222-11/inventory.json'
REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
KINDS = {'bjt', 'diode', 'zener', 'ic', 'inductor', 'transformer'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    inventory = json.loads(INVENTORY.read_text())
    register = json.loads(REGISTER.read_text())
    excluded = phase_a_review.converter_only_ids()
    with tempfile.TemporaryDirectory() as directory:
        assembled = steady_supply.assemble(Path(directory)/'assembly')
    by_id = defaultdict(list)
    for component in assembled['components']:
        by_id[component['source_id']].append(component)
    registered = {device['id']: device for device in register['devices']}
    if len(registered) != len(register['devices']):
        raise ValueError('duplicate A2 device register ID')
    families = defaultdict(list)
    rows = []
    for part in inventory['parts']:
        if part['kind'] not in KINDS or part['id'] in excluded:
            continue
        components = by_id.get(part['id'], [])
        if len(components) > 1:
            raise ValueError('device maps to multiple assembled components: '+part['id'])
        component = components[0] if components else None
        model = component['value'] if component else None
        entry = registered.get(part['id'])
        row = dict(id=part['id'], kind=part['kind'], printed_type=part.get('description'),
                   assembled_reference=component['reference'] if component else None,
                   active_model=model, register_model=entry['model'] if entry else None,
                   registered_parameter_keys=sorted(entry['parameters']) if entry else [])
        if entry and not component:
            raise ValueError('registered frame-path device absent from assembly: '+part['id'])
        if entry and entry['model'] != model:
            raise ValueError('registered model differs from live assembly: '+part['id'])
        rows.append(row)
        families[(part['kind'], part.get('description'))].append(row)
    rows.sort(key=lambda row: row['id'])
    groups = [dict(kind=kind, printed_type=printed_type,
                   ids=[row['id'] for row in members],
                   active_models=sorted({row['active_model'] for row in members
                                         if row['active_model']}),
                   registered_ids=[row['id'] for row in members if row['register_model']],
                   absent_from_assembly=[row['id'] for row in members
                                         if row['active_model'] is None])
              for (kind, printed_type), members in sorted(
                  families.items(), key=lambda item:(item[0][0], item[0][1] or ''))]
    return dict(format='dac-monitor-a2-device-coverage-v1',
                qualification='A2 gap inventory; registered rows are provisional, not completed model qualification',
                inventory_sha256=sha(INVENTORY), register_sha256=sha(REGISTER),
                assembly_source_sha256=phase_a_review.kicad_tree_hash(),
                inventory_device_instances=sum(p['kind'] in KINDS for p in inventory['parts']),
                frame_path_device_instances=len(rows),
                assembled_instances=sum(row['active_model'] is not None for row in rows),
                registered_instances=sum(row['register_model'] is not None for row in rows),
                absent_from_assembly=[row['id'] for row in rows if row['active_model'] is None],
                unregistered_assembled=[row['id'] for row in rows
                                        if row['active_model'] and not row['register_model']],
                families=groups, devices=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['registered_instances']}/{report['frame_path_device_instances']} "
          'frame-path device instances have provisional A2 register rows; '
          f"{len(report['absent_from_assembly'])} absent from the assembly")


if __name__ == '__main__':
    main()
