#!/usr/bin/env python3
"""Check a retained evidence tree, including nested archive manifests."""
import argparse,json
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def check(root):
    root=Path(root);manifest=root/'manifest.json';m=json.loads(manifest.read_text())
    files={str(p.relative_to(root)):sha(p) for p in root.rglob('*') if p.is_file() and p!=manifest}
    if files!=m['files']:raise ValueError('Changed or incomplete retained evidence')
    for name,digest in m['sources'].items():
        path=Path(name)
        if path.is_absolute() or '..' in path.parts:raise ValueError('Source must be relative to the verification directory')
        if sha(HERE/path)!=digest:raise ValueError('Changed evidence source: '+name)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('root',type=Path);a=p.parse_args();check(a.root)
    print('Retained files and source identities verified; full numerical/state review is separate.')
