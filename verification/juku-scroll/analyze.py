#!/usr/bin/env python3
"""Behavioral analysis of captures (Pillow required); no golden report hashes."""
import argparse
import csv
import hashlib
import json
import re
from pathlib import Path
from PIL import Image

def pixels(path):
    im=Image.open(path).convert('L').point(lambda x:255 if x else 0,'1')
    if im.size!=(320,241):raise ValueError(f'{path}: unexpected dimensions {im.size}')
    return im.tobytes()

def font_table(rom):
    # EKTA #0037: FF60 -> D7FB -> DD02, nine bitmap rows per glyph.
    return {b'\0'+rom[0x1d02+(c-32)*9:0x1d02+(c-31)*9]:chr(c) for c in range(32,127)}

def text_rows(data,font):
    return [''.join(font.get(bytes(data[(y*10+dy)*40+x] for dy in range(10)),'?')
                    for x in range(40)).rstrip() for y in range(24)]

def scroll_frames(paths,font):
    previous=None;shifts={1:0,10:0};seen=set();first={};last=None
    for path in paths:
        data=pixels(path);rows=[data[y*40:y*40+3] for y in range(241)]
        if previous is not None and rows!=previous:
            score={d:sum(a==b for a,b in zip(rows[40:72],previous[40+d:72+d])) for d in [0,1,10]}
            best=max(score,key=score.get)
            if best and score[best]>=28 and score[best]>score[0]+4:
                shifts[best]+=1;first.setdefault(str(best),path.name)
        previous=rows
        last=text_rows(data,font)
        for line in last:
            if re.fullmatch(r'[SNT][0-5][0-9] ABCDEFGHIJKLM',line):seen.add(line[:3])
    expected={f'{p}{i:02}' for p in 'SNT' for i in range(60)}
    return {'frames':len(paths),'one_pixel_up_transitions':shifts[1],'ten_pixel_up_transitions':shifts[10],
            'example_transition_frames':first,'numbered_lines_seen':len(seen),
            'missing_numbered_lines':sorted(expected-seen),'final_text':last,
            'completed':last is not None and 'SCROLL COMPLETE' in last and last[-1].startswith('A>')}

def analyze(root,rom_path):
    manifest=json.loads((root/'manifest.json').read_text());font=font_table(rom_path.read_bytes());results={}
    for name,case in manifest['cases'].items():
        engines={}
        for engine in ['native','mame']:
            folder=root/name/engine
            samples=list(csv.DictReader((folder/'capture.samples.csv').open()))
            # Flag history after the user sequence starts; reset RAM tests don't count.
            start=3.5 if case['context']=='monitor' else 15.5
            live=[r for r in samples if (int(r['cycle'])/2e6 if engine=='native' else float(r['seconds']))>=start]
            paths=sorted(folder.glob('capture-*.'+('pbm' if engine=='native' else 'png')))
            result={'final_pc':samples[-1]['pc'],'final_scroll_flag':samples[-1]['scroll_flag'],
                    'final_parsed_drive':samples[-1]['parsed_drive'],
                    'scroll_flags_observed':sorted({r['scroll_flag'] for r in live}),
                    'final_text':text_rows(pixels(paths[-1]),font),
                    'frame_count':len(paths)}
            if engine=='native':
                instructions=list(csv.DictReader((folder/'capture.instructions.csv').open()))
                received=bytes(int(r['a'],16) for r in instructions if r['pc']=='d9df')
                emitted=bytes(int(r['de'],16)&255 for r in instructions if r['pc']=='dcd1')
                result.update(received_keys_hex=received.hex(),console_output_prefix_hex=emitted[:96].hex(),
                              final_interrupt_enable=int(samples[-1]['iff']),
                              interrupt_acknowledgements_last_second=int(samples[-1]['frame_irqs'])-int(samples[-51]['frame_irqs']))
            if case['context']=='diagnostic':
                result.update(scroll_frames(paths,font))
                if (not result['completed'] or result['missing_numbered_lines'] or
                    not result['one_pixel_up_transitions'] or not result['ten_pixel_up_transitions']):
                    raise RuntimeError(f'{engine}: diagnostic scrolling acceptance failed')
            # Provenance only; never used as an acceptance gate.
            result['events_sha256']=hashlib.sha256((folder/'capture.events.csv').read_bytes()).hexdigest()
            engines[engine]=result
        results[name]=engines
    return {'provenance':manifest['provenance'],'cases':results}

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('captures',type=Path);p.add_argument('rom',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
    a.output.write_text(json.dumps(analyze(a.captures,a.rom),indent=2)+'\n')
