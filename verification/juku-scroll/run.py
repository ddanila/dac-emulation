#!/usr/bin/env python3
"""Run the issue-20 comparison. All generated files live in the output directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
from prepare import prepare

ROOT=Path(__file__).resolve().parents[2]
SEQUENCES={'plain':'','colon':'\x1b:','semicolon':'\x1b;', 'colon-q':'\x1b:\x11',
           'colon-x':'\x1b:x','colon-return':'\x1b:\r','q':'\x11','escape':'\x1b'}

def schedule(context,sequence,scale=1):
    rows=[]
    def type_at(t,text):
        for c in text:
            rows.extend([(t,ord(c),1),(t+round(120*scale),0,0)])
            t+=round(280*scale)
        return t
    type_at(2000, 'E' if context=='monitor' else 'TDD')
    start=4000 if context=='monitor' else 16000
    t=type_at(start,sequence)
    if context=='diagnostic': return rows,180000,17000
    if context=='monitor':
        t=type_at(t+1000,'abc\r'*4)
        type_at(t+1000,'\x03')
    else:
        # Return commits the input line; idle beforehand distinguishes a wait
        # from a crash. Later Ctrl-U/normal command tests continued responsiveness.
        t=type_at(t+1000,'dir\r')
        t=type_at(t+3000,'\x15dir\r')
        type_at(t+3000,'dir\r')
    return rows,max(30000,t+6000),start-500

def run_one(args,name,context,sequence,scale=1):
    case=args.output/name;case.mkdir()
    rows,end,from_ms=schedule(context,sequence,scale)
    keys=case/'input.keys';keys.write_text(''.join(f'{t} {k:02x} {d}\n' for t,k,d in rows))
    disk=args.output/'diagnostic.juk' if context=='diagnostic' else args.disk
    result={'context':context,'sequence_hex':sequence.encode().hex(),'hold_ms':round(120*scale),
            'gap_ms':round(160*scale),'end_ms':end,'engines':{}}
    for engine in ['native','mame']:
        dest=case/engine;dest.mkdir();prefix=dest/'capture'
        env=os.environ.copy()
        if engine=='native':
            cmd=[str(ROOT/'build/juku-scroll-capture'),str(args.rom),str(disk),str(prefix),str(keys),str(end),str(from_ms)]
        else:
            media=dest/'media.juk'
            shutil.copyfile(disk,media)
            media.chmod(0o444)
            env.update(JUKU_SCROLL_PREFIX=str(prefix),JUKU_SCROLL_KEYS=str(keys),JUKU_SCROLL_FROM=str(from_ms/1000),
                       SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
            cmd=[str(args.mame),'juku','-bios','3.43m_37','-rompath',str(args.roms),'-flop1',str(media),
                 '-video','none','-sound','none','-nothrottle','-seconds_to_run',str((end+999)//1000),
                 '-skip_gameinfo','-noreadconfig','-autoboot_delay','0','-autoboot_script',str(Path(__file__).with_name('mame.lua'))]
        completed=subprocess.run(cmd,cwd=dest,env=env,capture_output=True,text=True,timeout=240)
        (dest/'run.log').write_text(completed.stdout+completed.stderr)
        if completed.returncode or 'LUA ERROR' in completed.stdout+completed.stderr:
            raise RuntimeError(f'{name}/{engine} failed: {completed.stdout} {completed.stderr}')
        events=(dest/'capture.events.csv').read_text().splitlines()
        if sum(line.startswith('KEY,') for line in events)!=len(rows):
            raise RuntimeError(f'{name}/{engine}: input schedule did not run completely')
        if not (dest/'capture.ram').is_file():
            raise RuntimeError(f'{name}/{engine}: shutdown capture missing')
        result['engines'][engine]={'exit_code':completed.returncode,'command':cmd}
    (case/'case.json').write_text(json.dumps(result,indent=2)+'\n')
    print(name,'complete',flush=True)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--rom',type=Path,required=True);p.add_argument('--disk',type=Path,required=True)
    p.add_argument('--roms',type=Path,required=True);p.add_argument('--mame',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    for k in ['rom','disk','roms','mame','output']:setattr(a,k,getattr(a,k).resolve())
    a.output.mkdir(parents=True,exist_ok=False)
    subprocess.run(['make','build/juku-scroll-capture'],cwd=ROOT,check=True)
    provenance={k:hashlib.sha256(getattr(a,k).read_bytes()).hexdigest() for k in ['rom','disk']}
    provenance['core_revision']=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    provenance['mame_version']=subprocess.check_output([str(a.mame),'-help'],text=True).splitlines()[0]
    provenance['diagnostic']=prepare(a.disk,a.output/'diagnostic.juk')
    cases={}
    for context in ['ekdos','monitor']:
        for name,seq in SEQUENCES.items():
            key=context+'-'+name;cases[key]=run_one(a,key,context,seq)
    for scale in [0.5,2]:
        for name in ['plain','colon','colon-q']:
            key=f'ekdos-{name}-{scale}x';cases[key]=run_one(a,key,'ekdos',SEQUENCES[name],scale)
    cases['diagnostic']=run_one(a,'diagnostic','diagnostic','scroll\r')
    (a.output/'manifest.json').write_text(json.dumps({'provenance':provenance,'cases':cases},indent=2)+'\n')

if __name__=='__main__':main()
