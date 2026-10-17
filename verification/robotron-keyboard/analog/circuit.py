"""Electrical elements generated from the pinned reference connectivity."""
import hashlib
import json
import re
from pathlib import Path

REFERENCE = Path(__file__).resolve().parents[1] / 'reference'


def node(name):
    if not name:
        raise ValueError('Unconnected analog pin needs an explicit classification')
    return '0' if name == '/GND' else 'n_' + name.lstrip('/').replace('+', 'p')


def load():
    source = (REFERENCE / 'connectivity.json').read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != json.loads((REFERENCE / 'source.json').read_text())['sha256']:
        raise ValueError('Connectivity hash mismatch')
    components = json.loads(source)['components']
    nets = {n for c in components.values() for n in c['pins'].values() if n}
    if len({node(n) for n in nets}) != len(nets):
        raise ValueError('Analog net name collision')
    if any(not re.fullmatch('[A-Za-z0-9_]+', node(n)) for n in nets):
        raise ValueError('Unsupported SPICE net name')
    return components, digest


def value(text):
    if re.fullmatch(r'\d+k\d+', text):
        return text.replace('k', '.') + 'k'
    if re.fullmatch(r'\d+(?:\.\d+)?[pnumk]?', text):
        return text
    raise ValueError('Unsupported reference value: ' + text)


def elements(components, refs):
    """Return wiring and model membership; never silently omit a reference."""
    lines, models = [], {}
    for ref in refs:
        c = components[ref]
        pins, kind = c['pins'], c['type']
        if ref[0] in 'RC' and set(pins) == {'1', '2'}:
            model = 'capacitor' if ref[0] == 'C' else 'resistor'
            line = f'{ref} {node(pins["1"])} {node(pins["2"])} {value(kind)}'
        elif kind == 'DIODE' and set(pins) == {'A', 'K'}:
            model = 'D_NOMINAL'
            line = f'D{ref} {node(pins["A"])} {node(pins["K"])} {model}'
        elif kind in ('SC236D', 'SC308C') and set(pins) == {'B', 'C', 'E'}:
            model = 'NPN_NOMINAL' if kind == 'SC236D' else 'PNP_NOMINAL'
            line = f'Q{ref} ' + ' '.join(node(pins[p]) for p in ('C', 'B', 'E')) + ' ' + model
        else:
            raise ValueError('Unclassified analog component: ' + ref)
        lines.append(line)
        models[ref] = model
    return lines, models


def nominal_models(beta):
    return ['.model D_NOMINAL D(IS=1e-14 N=1)',
            f'.model NPN_NOMINAL NPN(IS=1e-14 BF={beta} VAF=100)',
            f'.model PNP_NOMINAL PNP(IS=1e-14 BF={beta} VAF=100)']
