"""Stream POSIX FIFO waveform output to lossless XZ without allocating the raw file."""
import contextlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

WORKER = '''
import hashlib,json,lzma,sys
h=hashlib.sha256();size=0
with open(sys.argv[1], 'rb') as source, lzma.open(sys.argv[2], 'wb', preset=int(sys.argv[3])) as target:
    for data in iter(lambda: source.read(1024*1024), b''):
        h.update(data);size+=len(data);target.write(data)
print(json.dumps({'sha256':h.hexdigest(),'bytes':size}))
'''


@contextlib.contextmanager
def capture(directory, names, enabled=True, *, preset=1):
    """The producer must finish inside the context; failures retain partial XZ files."""
    if type(preset) is not int or not 0 <= preset <= 9:
        raise ValueError("XZ preset must be an integer from 0 through 9")
    records = {}
    if not enabled:
        yield records
        return
    jobs = []
    try:
        for name in names:
            path = Path(directory) / name
            target = Path(str(path) + '.xz')
            partial = Path(str(target) + '.partial')
            if any(p.exists() or p.is_symlink() for p in (path, target, partial)):
                raise ValueError('Compressed capture requires fresh output paths: ' + str(path))
            os.mkfifo(path)
            jobs.append((path, target, partial, None))
            worker = subprocess.Popen([sys.executable, '-c', WORKER, str(path), str(partial), str(preset)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            jobs[-1] = path, target, partial, worker
        yield records
        for path, target, partial, worker in jobs:
            output, error = worker.communicate(timeout=60)
            if worker.returncode:
                raise ValueError('Waveform compression failed: ' + error.strip())
            record = json.loads(output)
            if not record['bytes']:
                raise ValueError('Empty compressed waveform: ' + str(path))
            records[path.name] = record
        # Publish only once every stream completed; validation reads through trace_io.
        for path, target, partial, worker in jobs:
            partial.replace(target)
    finally:
        for path, target, partial, worker in jobs:
            if worker is not None and worker.poll() is None:
                worker.terminate()
                try:
                    worker.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    worker.kill()
                    worker.communicate()
            if path.exists() and stat.S_ISFIFO(path.lstat().st_mode):
                path.unlink()
