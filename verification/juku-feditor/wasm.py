#!/usr/bin/env python3
"""Exercise FEDITOR via the public WASM runtime on a disposable writable disk."""
import argparse
import json
from pathlib import Path
import subprocess
from PIL import Image
from run import ROOT, sha, blank_intervals, physical


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', required=True, type=Path)
    p.add_argument('--comparison', required=True, type=Path)
    a = p.parse_args()
    root = a.comparison.resolve()
    dest = root / 'wasm-original'
    dest.mkdir(exist_ok=False)
    prefix = dest / 'capture'
    r = subprocess.run(['node', str(ROOT / 'verification/juku-feditor/wasm_capture.mjs'),
                        str(a.rom.resolve()), str(root / 'original.juk'), str(root / 'input.keys'),
                        str(prefix), '152000'], text=True, capture_output=True, timeout=300)
    (dest / 'run.log').write_text(r.stdout + r.stderr)
    if r.returncode:
        raise RuntimeError(str(dest / 'run.log'))
    metadata = json.loads(prefix.with_suffix('.json').read_text())
    assert metadata['keys'] == len((root / 'input.keys').read_text().splitlines())
    frames = [(int(p.stem.rsplit('-', 1)[1])/1000, p) for p in dest.glob('capture-*.pbm')]
    def at(t):
        path = min(frames, key=lambda x: abs(x[0]-t))[1]
        return Image.open(path).convert('L'), path
    blank = []
    for start, end in blank_intervals(root / 'native-original', 'native'):
        if end-start < .12:
            continue
        image, path = at((start+end)/2)
        assert image.size == (320, 241) and image.getbbox() is None
        blank.append({'time': (start+end)/2, 'sha256': sha(path)})
    editor, path = at(86)
    grid = sum((editor.getpixel((18+8*i, 112)) != 0) << (7-i) for i in range(8))
    assert grid & 0x7f == 0x6d
    # The public runtime must persist the same guest-created font file.
    raw = prefix.with_suffix('.juk').read_bytes()
    reference = (root / 'native-original/capture.juk').read_bytes()
    def file(raw):
        entries = [bytes(raw[physical(10240+i*32+j)] for j in range(32)) for i in range(128)]
        e = next(e for e in entries if e[0] == 0 and e[1:12] == b'TEST    LAT')
        return b''.join(bytes(raw[physical(10240+b*4096+i)] for i in range(4096))
                        for b in e[16:] if b)[:e[15]*128]
    assert file(raw) == file(reference) and len(file(raw)) == 1408
    result = {'wasm_sha256': sha(ROOT / 'dist/dac.wasm'), 'keys': metadata['keys'],
              'blank_frames_verified': blank, 'grid_first_row': hex(grid),
              'editor_frame_sha256': sha(path), 'saved_font_bytes_match_native': 1408}
    (root / 'wasm-results.json').write_text(json.dumps(result, indent=2)+'\n')


if __name__ == '__main__':
    main()
