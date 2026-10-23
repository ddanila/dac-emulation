#!/usr/bin/env python3
"""Archive recovery inputs and every accepted point in the reviewed event window.

Conditioning waveforms remain local; their original hashes are retained. This
is storage selection after analysis, not a changed simulation or acceptance
window. Failed runs retain their entire partial trace.
"""
import argparse
import hashlib
import io
import json
import lzma
from pathlib import Path
import shutil
import tarfile

from gate_switching_probe import sha


def retain(source,out):
    report=json.loads((source/'report.json').read_text())
    if not report['completed']:raise ValueError('Incomplete investigation')
    out.mkdir(parents=True,exist_ok=False)
    for name in ('report.json','assessment.json'):shutil.copyfile(source/name,out/name)
    receipt=dict(sourceSha256=sha(Path(__file__)),reportSha256=sha(source/'report.json'),artifacts={})
    with tarfile.open(out/'captures.tar.gz','w:gz') as tar:
        for name,digest in report['artifacts'].items():
            path=source/name
            if sha(path)!=digest:raise ValueError('Changed capture: '+name)
            data=path.read_bytes();entry=dict(originalSha256=digest)
            if name.endswith('/trace.txt.xz'):
                case=report['runs'][name.split('/')[0]]
                if case['completed']:
                    lines=lzma.decompress(data).splitlines(keepends=True)
                    begin=(case['preludeUs']-.5)*1e-6;end=(case['preludeUs']+1)*1e-6
                    selected=[line for line in lines[1:] if begin-1e-15 <= float(line.split()[0]) <= end+1e-15]
                    if not selected:raise ValueError('Empty event window')
                    data=lzma.compress(lines[0]+b''.join(selected))
                    entry.update(selection='Every accepted point in the already-reviewed event window.',
                                 intervalSeconds=[begin,end],rows=len(selected))
            entry['retainedSha256']=hashlib.sha256(data).hexdigest()
            receipt['artifacts'][name]=entry
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o644
            tar.addfile(info,io.BytesIO(data))
    receipt['archiveSha256']=sha(out/'captures.tar.gz')
    (out/'retention.json').write_text(json.dumps(receipt,indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();retain(a.source,a.out)
