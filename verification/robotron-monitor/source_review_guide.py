#!/usr/bin/env python3
"""Build a visual A1 review guide from the current unresolved source audit.

The guide shows evidence and source images. It never records a review decision.
"""
import argparse
import hashlib
import html
import json
from pathlib import Path

from phase_a_review import SCHEMATIC_PAGES, source_hash

SCHEMATIC_QUESTIONS = {
    3: ('Trace the external brightness R1 terminals and the handwritten X1 pin'
        ' corrections to the horizontal and neck-board nodes. Keep this control'
        ' distinct from the R28 dark-raster preset.'),
    4: ('Trace every T3 tap through the X1/X2 connectors, especially the auxiliary'
        ' SYNCH output and V14 cathode at TP17. Check the winding continuity and'
        ' polarity hypothesis before selecting a T3 candidate.'),
    9: ('Trace horizontal centring R4, L1/L2, R2 and bridge E1–E4 from X1:5/6'
        ' to the rails and deflection circuit. Determine the bridge position and'
        ' whether this branch can be represented with ideal converter rails.'),
    10: ('Trace width R5 through the A1 converter feedback and 41P/22P outputs.'
         ' Record which control effect would disappear with fixed ideal rails.'),
    16: ('Check the neck-board connector pin map and each diode direction before'
         ' accepting the mapped electrode test points.'),
    18: ('Check the assembly and external-control connector wiring, including'
         ' brightness and contrast. Treat handwritten component values as notes'
         ' until their applicability is established.'),
}


def build(audit, *, parts_images, schematic_images, source_pdf):
    if audit.get('format')!='dac-monitor-inventory-ocr-audit-v1' or len(audit.get('entries',[]))!=260:
        raise ValueError('expected complete 260-entry inventory audit')
    if hashlib.sha256(source_pdf.read_bytes()).hexdigest()!=source_hash():
        raise ValueError('source PDF hash differs from sources.json')
    open_entries=[entry for entry in audit['entries'] if entry['status']!='confirmed-by-3-passes']
    by_page={}
    for entry in open_entries:
        by_page.setdefault(entry['source_page'],[]).append(entry)
    def esc(value):
        return html.escape('' if value is None else str(value),quote=True)
    def image_link(path):
        if not path.is_file():
            raise ValueError('review page image is missing: '+str(path))
        uri=esc(path.resolve().as_uri())
        return f'<a href="{uri}">Open full-resolution page image</a><details><summary>Preview page image</summary><img src="{uri}" alt="Source page" loading="lazy"></details>'
    sections=[]
    for page,entries in sorted(by_page.items()):
        if page in SCHEMATIC_PAGES:
            path=schematic_images/f'page-{page}.png'
        else:
            path=parts_images/f'page_{page:03d}.png'
        rows=[]
        for entry in entries:
            readings=''.join('<li><strong>'+esc(tag)+'</strong>: '
                +esc(reading.get('description','ambiguous lines '+str(reading.get('ambiguous_lines'))))
                +(f' · article {esc(reading["article"])}' if reading.get('article') else '')
                +(' · review only' if tag in entry.get('review_only_passes',[]) else '')+'</li>'
                for tag,reading in sorted(entry.get('readings',{}).items()))
            rows.append('<tr><th scope="row">'+esc(entry['id'])+'</th><td>'
                +esc(entry['inventory_description'])+'</td><td>'+esc(entry['status'])
                +(f'<p>{esc(entry["source_conflict"])}</p>' if entry.get('source_conflict') else '')
                +'</td><td><ul>'+readings+'</ul></td></tr>')
        sections.append(f'<section id="page-{page}"><h2>Source page {page} · {len(entries)} open</h2>'
            +image_link(path)+f'<p><a href="{esc(source_pdf.resolve().as_uri())}#page={page}">Open source PDF at page {page}</a></p>'
            +'<table><thead><tr><th>Entry</th><th>Inventory description</th><th>Why open</th><th>Independent OCR readings</th></tr></thead><tbody>'
            +''.join(rows)+'</tbody></table></section>')
    schematic=[]
    for page in SCHEMATIC_PAGES:
        path=schematic_images/f'page-{page}.png'
        schematic.append(f'<section id="schematic-{page}"><h2>Schematic page {page}</h2>'
            +'<p>Check KiCad connectivity, diode direction and winding polarity against this source page.</p>'
            +f'<p><strong>Focused question:</strong> {esc(SCHEMATIC_QUESTIONS[page])}</p>'
            +image_link(path)+'</section>')
    style='body{font:16px system-ui,sans-serif;max-width:1300px;margin:auto;padding:1rem;color:#222}section{border-top:2px solid #555;padding:1rem 0}table{border-collapse:collapse;width:100%}th,td{border:1px solid #aaa;padding:.5rem;text-align:left;vertical-align:top}td ul{margin:0;padding-left:1.3rem}img{max-width:100%;height:auto}details{margin:.5rem 0}p{line-height:1.4}'
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Phase A source review guide</title>'
        +f'<style>{style}</style><h1>Phase A source review guide</h1><p>{len(open_entries)} open inventory entries across '
        +f'{len(by_page)} source pages, plus {len(SCHEMATIC_PAGES)} schematic pages. Compare each entry with the source image; '
        +'the OCR readings are aids, not decisions. Record identified human marks in the JSON template after review.</p>'
        +''.join(sections)+'<h1>Schematic connectivity review</h1>'+''.join(schematic)+'</html>\n')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit',type=Path,required=True)
    parser.add_argument('--source-pdf',type=Path,required=True)
    parser.add_argument('--parts-images',type=Path,required=True)
    parser.add_argument('--schematic-images',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    page=build(json.loads(args.audit.read_text()),parts_images=args.parts_images,
               schematic_images=args.schematic_images,source_pdf=args.source_pdf)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(page)
    print(args.output)


if __name__=='__main__':
    main()
