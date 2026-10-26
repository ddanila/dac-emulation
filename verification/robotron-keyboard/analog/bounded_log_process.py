"""Run a POSIX producer with lossless stdout/stderr capture and explicit budgets."""
import hashlib
import lzma
import math
import os
from pathlib import Path
import signal
import shutil
import subprocess
import threading
import time


def run(command, cwd, env, target, timeout, *, logical_limit, compressed_limit, min_free_bytes=0):
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError('Need finite positive timeout')
    if any(type(n) is not int or n <= 0 for n in (logical_limit, compressed_limit)):
        raise ValueError('Log limits must be positive integer byte counts')
    if type(min_free_bytes) is not int or min_free_bytes < 0:
        raise ValueError('Invalid free-space reserve')
    def check_space():
        if min_free_bytes and shutil.disk_usage(cwd).free < min_free_bytes:
            raise OSError('Capture free-space reserve exhausted')
    check_space()
    target = Path(target); partial = target.with_name(target.name + '.partial')
    if any(p.exists() or p.is_symlink() for p in (target, partial)):
        raise ValueError('Need fresh log output paths')
    usage = {'bytes': 0, 'compressedBytes': 0}; digest = hashlib.sha256()
    failures = []; finished = threading.Event(); start = time.monotonic()
    process = subprocess.Popen(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, start_new_session=True)

    class Sink:
        def __init__(self, stream): self.stream = stream
        def write(self, data):
            if usage['compressedBytes'] + len(data) > compressed_limit:
                raise ValueError('Compressed log budget exceeded')
            written = self.stream.write(data); usage['compressedBytes'] += written
            return written
        def flush(self): self.stream.flush()

    def drain():
        try:
            with process.stdout, partial.open('xb') as sink, lzma.open(Sink(sink), 'wb', preset=1) as dest:
                for data in iter(lambda: process.stdout.read(65536), b''):
                    if usage['bytes'] + len(data) > logical_limit:
                        raise ValueError('Logical log budget exceeded')
                    digest.update(data); usage['bytes'] += len(data); dest.write(data)
        except BaseException as exc:
            failures.append(exc)
        finally:
            finished.set()

    worker = threading.Thread(target=drain, daemon=True); worker.start()
    success = False; next_space_check = start
    try:
        while process.poll() is None or not finished.is_set():
            if failures: raise failures[0]
            if time.monotonic() >= next_space_check:
                check_space(); next_space_check = time.monotonic() + .5
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0: raise TimeoutError('Log producer timed out')
            # Event.wait would spin once draining finishes but a producer stays alive.
            time.sleep(min(.02, remaining))
        if failures: raise failures[0]
        worker.join()
        partial.replace(target); success = True
        return dict(usage, sha256=digest.hexdigest(), exitCode=process.returncode,
                    elapsedSeconds=time.monotonic()-start,
                    logicalLimitBytes=logical_limit, compressedLimitBytes=compressed_limit)
    finally:
        if not success:
            # Kill the entire producer group, including children retaining stdout.
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait(timeout=5)
            worker.join(timeout=5)
            if worker.is_alive(): raise RuntimeError('Log drain did not stop after producer termination')
