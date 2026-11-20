"""Streaming SHA-256 for monitor artifacts on the documented Python range."""
import hashlib
from pathlib import Path


def digest_stream(stream):
    value = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b''):
        value.update(chunk)
    return value.hexdigest()


def digest(path):
    with Path(path).open('rb') as stream:
        return digest_stream(stream)
