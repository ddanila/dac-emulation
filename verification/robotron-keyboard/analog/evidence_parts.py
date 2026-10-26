#!/usr/bin/env python3
"""Split opaque evidence into bounded files; restore identical bytes before review."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

BLOCK=1024*1024
DEFAULT_PART_BYTES=64*BLOCK


def pack(source, out, part_bytes=DEFAULT_PART_BYTES):
    source,out=Path(source),Path(out)
    if type(part_bytes) is not int or part_bytes<=0:raise ValueError('Need positive part size')
    if not source.is_file():raise ValueError('Need a completed regular evidence file')
    before=source.stat();out.mkdir(parents=True,exist_ok=False)
    manifest={'version':1,'originalName':source.name,'partLimitBytes':part_bytes,'bytes':0,'parts':[]}
    total=hashlib.sha256()
    with source.open('rb') as stream:
        while True:
            first=stream.read(min(BLOCK,part_bytes))
            if not first:break
            name=f'part-{len(manifest["parts"]):06d}';digest=hashlib.sha256();size=0
            with (out/name).open('xb') as target:
                data=first
                while data:
                    target.write(data);digest.update(data);total.update(data);size+=len(data)
                    data=stream.read(min(BLOCK,part_bytes-size)) if size<part_bytes else b''
            manifest['parts'].append({'name':name,'bytes':size,'sha256':digest.hexdigest()});manifest['bytes']+=size
    after=source.stat()
    if (before.st_size,before.st_mtime_ns)!=(after.st_size,after.st_mtime_ns) or manifest['bytes']!=before.st_size:
        raise ValueError('Source changed during packing; incomplete archive has no manifest')
    manifest['sha256']=total.hexdigest()
    with (out/'manifest.json').open('x') as f:json.dump(manifest,f,indent=2);f.write('\n')
    return manifest


def restore(archive, target):
    archive,target=Path(archive),Path(target)
    m=json.loads((archive/'manifest.json').read_text())
    if m['version']!=1 or type(m['partLimitBytes']) is not int or m['partLimitBytes']<=0:raise ValueError('Unsupported archive')
    if type(m['bytes']) is not int or m['bytes']<0:raise ValueError('Invalid total size')
    if target.exists():raise FileExistsError(target)
    total=hashlib.sha256();size=0
    with tempfile.NamedTemporaryFile(dir=target.parent,prefix='.evidence-',delete=False) as output:
        temporary=Path(output.name)
        try:
            for i,part in enumerate(m['parts']):
                if part['name']!=f'part-{i:06d}' or type(part['bytes']) is not int or not 0<part['bytes']<=m['partLimitBytes']:
                    raise ValueError('Invalid part identity or size')
                digest=hashlib.sha256();count=0
                with (archive/part['name']).open('rb') as stream:
                    for data in iter(lambda:stream.read(BLOCK),b''):
                        count+=len(data)
                        if count>part['bytes']:raise ValueError('Oversized part')
                        digest.update(data);total.update(data);output.write(data)
                if count!=part['bytes'] or digest.hexdigest()!=part['sha256']:raise ValueError('Changed part')
                size+=count
            if size!=m['bytes'] or total.hexdigest()!=m['sha256']:raise ValueError('Incomplete or changed archive')
            output.flush();os.fsync(output.fileno())
            # Publishing a verified file cannot overwrite an existing destination.
            os.link(temporary,target)
        finally:temporary.unlink()
    return {'bytes':size,'sha256':total.hexdigest()}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=['pack','restore'])
    p.add_argument('source',type=Path);p.add_argument('out',type=Path);a=p.parse_args()
    if a.mode=='pack':pack(a.source,a.out)
    else:restore(a.source,a.out)
