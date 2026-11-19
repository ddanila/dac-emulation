#!/usr/bin/env python3
"""Build a local, diagnostic-only visual guide for manual waveform review."""
import argparse
import hashlib
import html
import json
import math
from pathlib import Path

import calibration_contract
import phase_a_gates
import service_score

ROOT=Path(__file__).resolve().parent
SOURCES=ROOT/'sources.json'
BINS=512


def _source_image(path):
    path=Path(path).resolve()
    if not path.is_file():raise ValueError('missing manual waveform page image: '+str(path))
    return path.as_uri()


def _manual_pdf(path):
    path=Path(path).resolve()
    source=next(item for item in json.loads(SOURCES.read_text())['sources']
                if item['file']=='older-operation.pdf')
    if (not path.is_file() or path.stat().st_size!=source['bytes']
            or hashlib.sha256(path.read_bytes()).hexdigest()!=source['sha256']):
        raise ValueError('manual PDF differs from sources.json')
    return path.as_uri()


def _plot(point, bins, start, end):
    populated=[(i,lo,hi) for i,(lo,hi) in enumerate(bins) if lo is not None]
    if not populated:return '<p class="missing">Mapped probe is absent in this trace.</p>'
    low=min(lo for _,lo,_ in populated);high=max(hi for _,_,hi in populated)
    pad=max((high-low)*.08,abs(high)*.005,1e-9)
    low-=pad;high+=pad
    x0,x1,y0,y1=58,884,13,165
    x=lambda i:x0+(x1-x0)*i/(BINS-1)
    y=lambda value:y1-(value-low)/(high-low)*(y1-y0)
    bars=''.join(f'<path d="M{x(i):.1f} {y(lo):.1f}V{y(hi):.1f}"/>'
                 for i,lo,hi in populated)
    centers=' '.join(f'{x(i):.1f},{y((lo+hi)/2):.1f}' for i,lo,hi in populated)
    zero=(f'<path class="zero" d="M{x0} {y(0):.1f}H{x1}"/>'
          if low<=0<=high else '')
    label=lambda value:f'{value:.3g}'
    return (f'<svg viewBox="0 0 900 190" role="img" aria-label="{html.escape(point["model_expression"])} '
            f'from {start:.6g} to {end:.6g} seconds">'
            f'<rect x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}"/>'
            f'{zero}<g class="trace"><polyline points="{centers}"/>{bars}</g>'
            f'<text x="4" y="18">{label(high)} V</text>'
            f'<text x="4" y="164">{label(low)} V</text>'
            f'<text x="{x0}" y="184">{start*1000:.3f} ms</text>'
            f'<text x="{x1}" y="184" text-anchor="end">{end*1000:.3f} ms</text>'
            '</svg>')


def make_guide(score, manual_pdf, page_images):
    """Use exact scored samples; min/max bins retain narrow flyback spikes."""
    phase_a_gates.verify_service_score(score)
    window=score.get('requested_window_s')
    if (not isinstance(window,list) or len(window)!=2
            or not all(type(t) in (int,float) and math.isfinite(t) for t in window)
            or not window[0]<window[1]):
        raise ValueError('waveform guide needs a bounded service-score window')
    manual_uri=_manual_pdf(manual_pdf)
    image_uris={page:_source_image(path) for page,path in page_images.items()}
    register=json.loads(service_score.REGISTER.read_text())
    source_pages={w['test_point']:w['source']['page'] for w in register['waveforms']}
    points={p['test_point']:p for p in score['points']}
    if set(points)!=set(range(1,18)) or any(source_pages[n] not in image_uris for n in points):
        raise ValueError('manual waveform pages or test points are missing')
    spans={n:(window[0] if n<=8 else max(window[0],window[1]-4*62.5e-6),window[1])
           for n in points}
    bins={n:[[None,None] for _ in range(BINS)] for n in points}
    expressions={n:points[n]['model_expression'].lower() for n in points}
    for row in service_score.samples(score['input']):
        t=row['time']
        if t<window[0]:continue
        if t>window[1]:break
        for n,name in expressions.items():
            a,b=spans[n]
            if t<a or name not in row:continue
            value=row[name]
            if not math.isfinite(value):raise ValueError('nonfinite plotted waveform')
            slot=min(BINS-1,int((t-a)/(b-a)*(BINS-1)))
            bucket=bins[n][slot]
            bucket[0]=value if bucket[0] is None else min(bucket[0],value)
            bucket[1]=value if bucket[1] is None else max(bucket[1],value)
    escape=html.escape
    parts=['<!doctype html><html lang="en"><meta charset="utf-8">',
           '<title>K7222 waveform review guide</title>',
           '<style>body{font:16px system-ui,sans-serif;max-width:1100px;margin:auto;padding:1rem;color:#222}'
           'section{border-top:2px solid #777;padding:1rem 0}p{line-height:1.4}'
           'svg{width:100%;background:#fafafa}svg rect{fill:none;stroke:#aaa}'
           'svg .trace{fill:none;stroke:#123b8a;stroke-width:1}svg .zero{stroke:#aaa;stroke-dasharray:4 3}'
           'svg text{font:11px system-ui,sans-serif;fill:#444}.missing{color:#a00}</style>',
           '<h1>K7222 manual waveform review</h1>',
           '<p>This guide is diagnostic only. Plots show the exact scored window; horizontal points '
           'show its final four line periods. Each vertical line preserves the minimum and maximum '
           'sample in a time bin. The hash-checked PDF is authoritative; page images are local '
           'previews. This guide is for investigating scorer failures.</p>',
           f'<p>Score SHA-256: <code>{calibration_contract.digest(score)}</code><br>'
           f'Trace SHA-256: <code>{escape(score["input_sha256"])}</code><br>'
           f'Register SHA-256: <code>{escape(score["register_sha256"])}</code></p>']
    for page in sorted(image_uris):
        uri=image_uris[page]
        parts.append(f'<details><summary>Manual waveform page {page}</summary>'
                     f'<p><a href="{manual_uri}#page={page}">Open source PDF page {page}</a></p>'
                     f'<img src="{uri}" alt="Manual waveform page {page}" style="max-width:100%"></details>')
    for n in sorted(points):
        point=points[n];ref=point['reference'];measured=point.get('measured',{})
        page=source_pages[n];a,b=spans[n]
        target=ref['peak_to_peak_v'] or ref['peak_to_peak_range_v']
        actual=measured.get('peak_to_peak_v')
        actual_text=f'{actual:.3g} Vpp' if actual is not None else 'unmeasured'
        parts.append(f'<section id="tp{n}"><h2>Test point {n} · {escape(point["source_node"])}</h2>'
                     f'<p>Model: <code>{escape(point["model_expression"])}</code> · '
                     f'Numeric status: <strong>{escape(point["status"])}</strong> · '
                     f'Vpp: {actual_text} / guideline {escape(str(target))}</p>'
                     f'<p>Manual shape: {escape(str(ref["shape_class"]))}; '
                     f'polarity: {escape(str(ref["polarity"]))}. '
                     f'Instrument: {escape(str(ref["instrument"]))}. '
                     f'{escape(str(ref["operating_conditions"]))} '
                     f'<a href="{manual_uri}#page={page}">Source page {page}</a>.</p>'
                     +_plot(point,bins[n],a,b)+'</section>')
    return '\n'.join(parts+['</html>'])+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--service-score',type=Path,required=True)
    parser.add_argument('--manual-pdf',type=Path,required=True)
    parser.add_argument('--page-20-image',type=Path,required=True)
    parser.add_argument('--page-21-image',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    score=json.loads(args.service_score.read_text())
    guide=make_guide(score,args.manual_pdf,{20:args.page_20_image,21:args.page_21_image})
    args.output.parent.mkdir(parents=True,exist_ok=True)
    with args.output.open('x') as stream:stream.write(guide)
    print(args.output)


if __name__=='__main__':main()
