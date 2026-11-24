#!/usr/bin/env python3
"""Compare unchanged BDOS file I/O on native, WASM and MAME."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from guest import verify
from analyze import pixels,text_rows,font_table

def main():
    p=argparse.ArgumentParser()
    for name in ('library','wasm','mame','roms','rom','disk','output'):
        p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    for name in vars(a):setattr(a,name,getattr(a,name).resolve())
    a.output.mkdir(parents=True,exist_ok=False)
    here=Path(__file__).resolve().parent
    subprocess.run([sys.executable,str(here/'accept.py'),'--library',str(a.library),
                    '--rom',str(a.rom),'--disk',str(a.disk),'--output',str(a.output/'native')],check=True)
    source=a.output/'native/guest.juk';keys=a.output/'native/input.keys'
    subprocess.run(['node',str(here/'accept.mjs'),str(a.wasm),str(a.rom),str(source),
                    str(keys),str(a.output/'wasm')],check=True)
    dest=a.output/'mame';dest.mkdir();media=dest/'media.juk';shutil.copyfile(source,media)
    env=os.environ.copy();env.update(JUKU_SCROLL_SCRIPT=str(here.parent/'juku-scroll/mame.lua'),
        JUKU_SCROLL_PREFIX=str(dest/'capture'),JUKU_SCROLL_KEYS=str(keys),JUKU_SCROLL_FROM='89.8',
        SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
    cmd=[str(a.mame),'juku','-bios','3.43m_37','-rompath',str(a.roms),'-flop1',str(media),
        '-video','none','-sound','none','-nothrottle','-seconds_to_run','90','-skip_gameinfo',
        '-noreadconfig','-autoboot_delay','0','-autoboot_script',str(here/'mame.lua')]
    r=subprocess.run(cmd,cwd=dest,env=env,capture_output=True,text=True,timeout=180)
    (dest/'run.log').write_text(r.stdout+r.stderr)
    assert r.returncode==0 and 'LUA ERROR' not in r.stdout+r.stderr
    assert sum(line.startswith('KEY,') for line in (dest/'capture.events.csv').read_text().splitlines())==len(keys.read_text().splitlines())
    assert (dest/'capture.ram').exists()
    report={'provenance':{'core_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=here,text=True).strip(),
        'rom_sha256':hashlib.sha256(a.rom.read_bytes()).hexdigest(),
        'disk_sha256':hashlib.sha256(a.disk.read_bytes()).hexdigest(),
        'mame_version':subprocess.check_output([str(a.mame),'-help'],text=True).splitlines()[0]},'engines':{}}
    font=font_table(a.rom.read_bytes());before=source.read_bytes()
    for name,disk,frame in [('native',a.output/'native/written.juk',a.output/'native/final.pbm'),
        ('wasm',a.output/'wasm.juk',a.output/'wasm.pbm'),
        ('mame',media,sorted(dest.glob('capture-*.png'))[-1])]:
        rows=text_rows(pixels(frame),font)
        assert 'FDC25 PASS' in rows and any(row.startswith('A>') for row in rows[rows.index('FDC25 PASS')+1:]),rows
        result=verify(before,disk.read_bytes())
        result.update(final_text=rows,disk_sha256=hashlib.sha256(disk.read_bytes()).hexdigest())
        report['engines'][name]=result
    (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    print('Native, WASM and MAME guest file I/O PASS')

if __name__=='__main__':main()
