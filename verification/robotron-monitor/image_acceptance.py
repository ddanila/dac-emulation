#!/usr/bin/env python3
"""Compare archived linear CRT frames without registration or exposure fitting.

This optical gate does not certify electrical settling, source provenance, a
complete monitor, or a physical specimen. It consumes stream_render archives.
"""
import argparse
import array
import hashlib
import json
import math
from pathlib import Path
import sys
import phosphor
import sustained

LIMIT = .02


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Archive:
    def __init__(self, directory, first_frame):
        self.root = Path(directory).resolve()
        self.manifest_hash = digest(self.root / 'render.json')
        self.data = json.loads((self.root / 'render.json').read_text())
        if self.data.get('status') != 'complete':
            raise ValueError('incomplete render archive')
        if 'input.csv' not in self.data.get('hashes', {}):
            raise ValueError('missing electrical input hash')
        self.verify_inputs()
        self.p = phosphor.parameters(self.data['surface_parameters'])
        expected = dict(dtype='little-endian float32', unit='W/m^2', order='row-major',
                        width=self.p['width'], height=self.p['height'])
        if self.data.get('linear_format') != expected:
            raise ValueError('unsupported linear format')
        frames = self.data['linear_frames']
        if type(first_frame) is not int or first_frame < 0:
            raise ValueError('invalid first frame')
        if len(frames) != self.data['frames'] or len(frames) < first_frame + sustained.FIELDS:
            raise ValueError('sixteen original output frames required')
        self.frames = frames[first_frame:first_frame + sustained.FIELDS]
        times = [f['time_s'] for f in self.frames]
        if any(type(t) not in (int, float) or not math.isfinite(t) or t < 0 for t in times):
            raise ValueError('invalid frame time')
        periods = [b-a for a, b in zip(times, times[1:])]
        if min(periods) <= 0 or (max(periods)-min(periods))/(sum(periods)/len(periods)) >= .01:
            raise ValueError('nonregular frame times')
        if len({f['path'] for f in self.frames}) != sustained.FIELDS:
            raise ValueError('reused frame path')
        self.areas = phosphor.Surface(self.p).areas
        self.provenance = dict(manifest_sha256=self.manifest_hash, first_frame=first_frame,
                               frames=self.frames, surface_parameters=self.p)

    def verify_inputs(self):
        for name, expected in self.data['hashes'].items():
            path = (self.root / name).resolve()
            if not path.is_relative_to(self.root) or digest(path) != expected:
                raise ValueError('render input or model hash mismatch')

    def read(self, index):
        entry = self.frames[index]
        path = (self.root / entry['path']).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('frame outside archive')
        if path.stat().st_size != 4*len(self.areas) or digest(path) != entry['sha256']:
            raise ValueError('linear frame size or hash mismatch')
        pixels = array.array('f')
        with path.open('rb') as stream:
            pixels.fromfile(stream, len(self.areas))
        if sys.byteorder != 'little':
            pixels.byteswap()
        # Hash the bytes actually read too, so replacing a file during import
        # cannot pass merely because its earlier on-disk hash matched.
        raw = array.array('f', pixels)
        if sys.byteorder != 'little':
            raw.byteswap()
        if hashlib.sha256(raw.tobytes()).hexdigest() != entry['sha256']:
            raise ValueError('linear frame changed during import')
        if any(not math.isfinite(v) or v < 0 for v in pixels):
            raise ValueError('invalid linear irradiance')
        if not any(pixels):
            raise ValueError('dark frame cannot establish image acceptance')
        return pixels

    def unchanged(self):
        if digest(self.root / 'render.json') != self.manifest_hash:
            raise ValueError('render manifest changed during comparison')
        for i in range(sustained.FIELDS):
            self.read(i)
        self.verify_inputs()


def error(a, b, areas):
    """Area-weighted relative L2, conservative for either image as reference."""
    denominator = min(math.fsum(x*x*w for x, w in zip(a, areas)),
                      math.fsum(x*x*w for x, w in zip(b, areas)))
    if denominator <= 0:
        raise ValueError('zero image norm')
    return math.sqrt(math.fsum((x-y)**2*w for x, y, w in zip(a, b, areas))/denominator)


def project(pixels, fine, coarse):
    """Conserve emitted optical power when aggregating fine spherical cells."""
    cw, ch = coarse.p['width'], coarse.p['height']
    fw, fh = fine.p['width'], fine.p['height']
    if fw % cw or fh % ch or fw//cw != fh//ch or fw//cw < 2:
        raise ValueError('spatial refinement requires an integer uniform scale >= 2')
    scale = fw//cw
    result = array.array('d', [0.])*(cw*ch)
    for y in range(ch):
        for x in range(cw):
            result[y*cw+x] = math.fsum(
                pixels[(y*scale+dy)*fw+x*scale+dx]*fine.areas[(y*scale+dy)*fw+x*scale+dx]
                for dy in range(scale) for dx in range(scale))/coarse.areas[y*cw+x]
    return result


def temporal(archive):
    worst = dict(error=0., frames=[0, 1])
    # Every pair, rather than adjacent frames only: slow drift must fail too.
    # Only two full images are retained at once.
    for i in range(sustained.FIELDS):
        a = archive.read(i)
        for j in range(i+1, sustained.FIELDS):
            value = error(a, archive.read(j), archive.areas)
            if value > worst['error']:
                worst = dict(error=value, frames=[i, j])
    return worst


def assess(directory, *, first_frame=0, refined=None, refined_first_frame=None):
    base = Archive(directory, first_frame)
    report = dict(format='dac-crt-image-acceptance-v1', accepted=False,
                  qualification='optical-image-checks-only',
                  full_monitor_qualified=False, specimen_validated=False,
                  temporal_stability=False, spatial_refinement=False,
                  limit=LIMIT, metric='curved-area-weighted relative L2 / smaller image norm',
                  registration=False, brightness_normalization=False,
                  source_content_verified=False, electrical_refinement_verified=False,
                  evaluator_sha256=digest(Path(__file__)),
                  base=base.provenance, failures=[])
    worst = temporal(base)
    report['temporal_worst'] = worst
    report['temporal_stability'] = worst['error'] < LIMIT
    if not report['temporal_stability']:
        report['failures'].append('linear image changes across output fields')
    if refined is None:
        report['failures'].append('missing spatial refinement run')
    else:
        fine = Archive(refined, first_frame if refined_first_frame is None else refined_first_frame)
        keys = set(base.p)-{'width', 'height'}
        if any(base.p[k] != fine.p[k] for k in keys):
            raise ValueError('physical surface or display parameters changed')
        if [f['time_s'] for f in base.frames] != [f['time_s'] for f in fine.frames]:
            raise ValueError('refinement frame times differ; alignment is not allowed')
        # This comparison isolates spatial discretization: unchanged electrical
        # input and optical code. Electrical refinement is a separate gate.
        if not base.data.get('hashes') or base.data['hashes'] != fine.data.get('hashes'):
            raise ValueError('spatial refinement changed electrical input or optical model')
        errors = [error(base.read(i), project(fine.read(i), fine, base), base.areas)
                  for i in range(sustained.FIELDS)]
        report['refined'] = fine.provenance
        report['refined_temporal_worst'] = temporal(fine)
        if report['refined_temporal_worst']['error'] >= LIMIT:
            report['temporal_stability'] = False
            report['failures'].append('refined linear image changes across output fields')
        report['spatial_errors'] = errors
        report['spatial_refinement'] = max(errors) < LIMIT
        if not report['spatial_refinement']:
            report['failures'].append('spatial refinement changes linear image')
        fine.unchanged()
    base.unchanged()
    report['accepted'] = not report['failures']
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--render', type=Path, required=True)
    parser.add_argument('--refined', type=Path)
    parser.add_argument('--first-frame', type=int, default=0)
    parser.add_argument('--refined-first-frame', type=int)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = assess(args.render, first_frame=args.first_frame, refined=args.refined,
                    refined_first_frame=args.refined_first_frame)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
        stream.write('\n')
    raise SystemExit(0 if result['accepted'] else 2)
