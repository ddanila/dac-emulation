"""Read retained waveforms without requiring their uncompressed disk allocation."""
import gzip
from pathlib import Path


def open_binary(path):
    path = Path(path)
    return path.open('rb') if path.exists() else gzip.open(str(path) + '.gz', 'rb')


def open_text(path):
    path = Path(path)
    return path.open() if path.exists() else gzip.open(str(path) + '.gz', 'rt')
