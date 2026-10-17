"""Read retained waveforms without requiring their uncompressed disk allocation."""
import gzip
import io
import lzma
from pathlib import Path


def open_binary(path):
    path = Path(path)
    if path.exists():
        return path.open('rb')
    if Path(str(path) + '.gz').exists():
        return gzip.open(str(path) + '.gz', 'rb')
    return lzma.open(str(path) + '.xz', 'rb')


def open_text(path):
    return io.TextIOWrapper(open_binary(path))
