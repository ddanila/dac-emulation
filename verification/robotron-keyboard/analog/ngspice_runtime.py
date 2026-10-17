"""Fingerprint the executable and explicit XSPICE initialization used by a run."""
import hashlib
import os
import shlex
import shutil
from pathlib import Path


def fingerprint(path):
    path = Path(path).resolve(strict=True)
    return {'path': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}


def identify(executable, spinit=None):
    located = shutil.which(str(executable))
    if located is None:
        raise ValueError('ngspice executable not found: ' + str(executable))
    binary = Path(located).resolve()
    if spinit is None:
        scripts = Path(os.environ.get('SPICE_SCRIPTS', binary.parent.parent / 'share/ngspice/scripts'))
        spinit = scripts / 'spinit'
    spinit = Path(spinit).resolve(strict=True)
    if spinit.name != 'spinit':
        raise ValueError('The selected ngspice initialization file must be named spinit')
    models = []
    for line in spinit.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('*'):
            continue
        words = shlex.split(line)
        if words and words[0].lower() == 'codemodel':
            if len(words) != 2 or not Path(words[1]).is_absolute() or '$' in words[1]:
                raise ValueError('Qualification requires literal absolute codemodel paths in spinit')
            models.append(fingerprint(words[1]))
        if words and words[0].lower() in ('source', '.include'):
            raise ValueError('Nested initialization files require explicit runtime provenance')
    if not models:
        raise ValueError('No explicit XSPICE code models in selected spinit')
    runtime = {'executable': fingerprint(binary), 'spinit': fingerprint(spinit), 'codeModels': models}
    env = dict(os.environ)
    env['SPICE_SCRIPTS'] = str(spinit.parent)
    return runtime, env


def verify(runtime):
    for item in [runtime['executable'], runtime['spinit'], *runtime['codeModels']]:
        if fingerprint(item['path']) != item:
            raise ValueError('ngspice runtime changed during execution: ' + item['path'])
