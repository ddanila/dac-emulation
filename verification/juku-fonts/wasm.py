#!/usr/bin/env python3
"""Verify the unmodified applications through the already-built public WASM API."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[2]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--rom', type=Path, required=True)
    p.add_argument('--comparison', type=Path, required=True)
    a = p.parse_args()
    result = {'wasm_sha256': hashlib.sha256((ROOT / 'dist/dac.wasm').read_bytes()).hexdigest(),
              'rom_sha256': hashlib.sha256(a.rom.read_bytes()).hexdigest(), 'cases': {}}
    for app in ['mfd', 'bowling']:
        case = a.comparison / (app + '-original')
        dest = case / 'wasm'
        dest.mkdir(exist_ok=False)
        prefix = dest / 'capture'
        command = ['node', str(ROOT / 'verification/juku-scroll/wasm_capture.mjs'),
                   str(a.rom.resolve()), str((case / 'media.juk').resolve()),
                   str((case / 'input.keys').resolve()), str(prefix.resolve()), '30000']
        r = subprocess.run(command, capture_output=True, text=True, timeout=240)
        (dest / 'run.log').write_text(r.stdout + r.stderr)
        if r.returncode:
            raise RuntimeError('WASM capture failed')
        frames = list(dest.glob('capture-*.pbm'))
        final = max(frames, key=lambda f: int(f.stem.rsplit('-', 1)[1]))
        image = Image.open(final).convert('1')
        native = Image.open(case / 'native/capture.pbm').convert('1')
        assert image.size == native.size == (320, 241)
        diff = ImageChops.difference(image, native)
        allowed = Image.new('1', image.size)
        if app == 'bowling':
            ImageDraw.Draw(allowed).rectangle((240, 150, 247, 159), fill=255)
        assert ImageChops.subtract(diff, allowed).getbbox() is None
        result['cases'][app] = {'screen_matches_native_except_cursor': True,
            'different_pixels': sum(bool(v) for v in diff.getdata()), 'difference_bounds': diff.getbbox(),
            'frame_sha256': hashlib.sha256(final.read_bytes()).hexdigest()}
    (a.comparison / 'wasm-results.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
