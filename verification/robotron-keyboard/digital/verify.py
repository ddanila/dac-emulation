#!/usr/bin/env python3
"""Verify retained qualification evidence without rerunning firmware or accepting its failures."""
import gzip,json,tarfile,tempfile
from pathlib import Path
from qualify import BOARD,sha
from review import review

def verify():
    root=Path(__file__).resolve().parent/'reports';receipt=json.loads((root/'receipt.json').read_text())
    for name,digest in receipt['files'].items():
        if sha(root/name)!=digest:raise ValueError('Changed retained artifact: '+name)
    producer=json.loads((root/'assessment.json').read_text());completion=json.loads((root/'completion.json').read_text())
    with tempfile.TemporaryDirectory() as temp:
        dest=Path(temp).resolve()
        with tarfile.open(root/'captures.tar.gz') as archive:
            for member in archive:
                path=dest/member.name
                if not member.isfile() or not path.resolve().is_relative_to(dest):raise ValueError('Unsafe capture member')
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(archive.extractfile(member).read())
        if json.loads(json.dumps(review(producer,dest)))!=completion:raise ValueError('Completion review is stale')
    candidate=json.loads((root/'t2write-reset/assessment.json').read_text())
    import hashlib
    if hashlib.sha256(gzip.decompress((root/'t2write-reset/hdl.txt.gz').read_bytes())).hexdigest()!=candidate['hdlSha256']:raise ValueError('Changed candidate trace')
    if candidate['producerSha256']!=sha(Path(__file__).parent/'write_phase.py'):raise ValueError('Changed candidate producer')
    print('Retained captures and completion review verified; open gates remain open')
if __name__=='__main__':verify()
