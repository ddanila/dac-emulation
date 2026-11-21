"""Audit discrete devices inside the active frame-path IC equivalents.

This checks the selected subcircuits' own model declarations. It does not
qualify their assumed silicon or the behavioral sources around the devices.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from a2_implicit_default_audit import CRITICAL, ROOT, declaration


REGISTER = ROOT/'reference/k7222-11/device-model-register.json'
PROFILES = (ROOT/'profiles/k7222-11-vertical-integrator.json',
            ROOT/'profiles/k7222-11-vertical-output.json')
ACTIVE = ('012-6931:A2', '012-6931:A3')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def subcircuit(path, name):
    source = re.sub(r'\n\s*\+\s*', ' ', path.read_text())
    matches = re.findall(r'^\.subckt\s+'+re.escape(name)+r'\b([^\n]*)\n(.*?)^\.ends\s+'+re.escape(name)+r'\s*$',
                         source, re.I | re.M | re.S)
    if len(matches) != 1:
        raise ValueError(f'expected one subcircuit {name} in {path}')
    return matches[0][1]


def run():
    register = json.loads(REGISTER.read_text())
    entries = {row['id']: row for row in register['devices']}
    profiles = [json.loads(path.read_text()) for path in PROFILES]
    rows = []
    for source_id in ACTIVE:
        entry = entries[source_id]
        name = entry['model']
        path = ROOT/entry['model_file']
        if not any(name in profile['subcircuits'] for profile in profiles):
            raise ValueError('active subcircuit missing from vertical profiles: '+name)
        body = subcircuit(path, name)
        devices = []
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith('*'):
                continue
            tokens = stripped.split()
            if tokens[0][0].upper() not in ('Q', 'D'):
                continue
            model = tokens[-1]
            found = declaration(path, model)
            if found is None:
                raise ValueError(f'internal device {tokens[0]} has no model: {model}')
            kind, explicit = found
            if (tokens[0][0].upper() == 'Q') != (kind in ('NPN', 'PNP')):
                raise ValueError(f'internal device/model type mismatch: {tokens[0]}')
            devices.append(dict(reference=tokens[0], model=model, model_type=kind,
                                explicit_parameters=sorted(explicit),
                                critical_implicit_defaults=sorted(CRITICAL[kind]-explicit)))
        rows.append(dict(source_id=source_id, subcircuit=name, model_file=entry['model_file'],
                         model_sha256=sha(path), devices=devices))
    return dict(format='dac-monitor-a2-internal-device-audit-v1',
                qualification='selected frame-path IC equivalents only; model-default inventory, not silicon qualification',
                register_sha256=sha(REGISTER),
                profile_sha256={path.name: sha(path) for path in PROFILES},
                screened_parameters={kind: sorted(keys) for kind, keys in CRITICAL.items()},
                rows=rows,
                internal_discrete_instances=sum(len(row['devices']) for row in rows),
                instances_with_critical_defaults=sum(bool(device['critical_implicit_defaults'])
                                                     for row in rows for device in row['devices']),
                remaining='Explicitly bound the selected MAA723 internal pass, limit and clamp models, then rerun its class check and affected vertical-stage checks. The P09A equivalent has behavioral elements only; its parameter bounds and connected-stage qualification remain separate A2 work.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2)+'\n')
    print(f"{report['instances_with_critical_defaults']} of {report['internal_discrete_instances']} internal devices use screened implicit defaults")
