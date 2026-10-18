"""Screen local SN74LS00 IBIS package pin/model assignments before model import.

This is deliberately not a general IBIS validator or permission to substitute
SN74LS00 behavior for DL000. Vendor tables are not copied into the repository.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

INPUTS = {1, 2, 4, 5, 9, 10, 12, 13}
OUTPUTS = {3, 6, 8, 11}


def inspect(text):
    components, models = {}, {}
    component = model = section = None
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.partition('|')[0].strip()
        if not line:
            continue
        match = re.match(r'^\[([^]]+)\]\s*(.*)$', line)
        if match:
            section, value = match[1].lower(), match[2].strip()
            if section == 'component':
                if not value or value in components:
                    raise ValueError(f'Duplicate or empty component at line {number}')
                component, model = value, None
                components[component] = {}
            elif section == 'model':
                if not value or value in models:
                    raise ValueError(f'Duplicate or empty model at line {number}')
                model, component = value, None
                models[model] = None
            continue
        words = line.split()
        if section == 'pin':
            if component is None or len(words) < 3 or not words[0].isdigit():
                raise ValueError(f'Invalid pin row at line {number}')
            pin = int(words[0])
            if pin in components[component]:
                raise ValueError(f'Duplicate pin at line {number}')
            components[component][pin] = words[1:3]
        elif section == 'model' and words[0].lower() == 'model_type':
            if model is None or len(words) != 2 or models[model] is not None:
                raise ValueError(f'Invalid model type at line {number}')
            models[model] = words[1].lower()
    if not components or not models or any(v is None for v in models.values()):
        raise ValueError('Missing component or model type')
    results = {}
    for name, pins in components.items():
        errors = []
        for pin in sorted(set(pins) | set(range(1, 15))):
            expected = ('input' if pin in INPUTS else 'output' if pin in OUTPUTS
                        else 'gnd' if pin == 7 else 'power' if pin == 14 else None)
            if pin not in pins:
                errors.append({'pin': pin, 'reason': 'missing pin', 'expectedType': expected})
                continue
            signal, assigned = pins[pin]
            actual = assigned.lower() if assigned.upper() in ('POWER', 'GND') else models.get(assigned)
            if expected is None or actual != expected:
                errors.append({'pin': pin, 'signal': signal, 'assignedModel': assigned,
                               'actualType': actual, 'expectedType': expected})
        results[name] = {'pinAssignmentPassed': not errors, 'errors': errors}
    return {'qualified': False, 'pinAssignmentPassed': all(x['pinAssignmentPassed'] for x in results.values()),
            'components': results,
            'scope': 'Standard 14-pin LS00 input/output/supply roles only; not table syntax, numerical curves, timing, package parasitics, DL000 equivalence or device qualification.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ibis', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    raw = args.ibis.read_bytes()
    result = inspect(raw.decode('latin-1'))
    result.update(nonAsciiBytes=sum(byte > 127 for byte in raw),
                  sourceSha256=hashlib.sha256(raw).hexdigest(),
                  scriptSha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  sourceUrl='https://www.ti.com/lit/ibs/SDLM003',
                  pinRoleReference='https://www.ti.com/lit/gpn/SN74LS00',
                  decision='Do not import a failing package pin map. A passing pin map alone does not validate the electrical tables or authorize a DL000 substitution.')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    return 0 if result['pinAssignmentPassed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
