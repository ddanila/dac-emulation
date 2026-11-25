#!/usr/bin/env python3
"""Issue #13: CPU-driven memory-window probes and preserved D6 decode evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
SAMPLES=(0x1000,0x3fff,0x4000,0x5fff,0x6000,0x7fff,0x8000,0x87ff,
         0x8800,0xbfff,0xc000,0xd7ff,0xd800,0xffff)
NEIGHBORS=(0x1000,0x3fff,0xc000,0xd7ff,0xd800,0xffff)


def guest(mode):
    code=bytearray([0xf3])  # DI: isolate memory mapping from interrupt firmware.
    def emit(*v): code.extend(v)
    def word(op,a): emit(op,a&255,a>>8)
    def out(p,v): emit(0x3e,v,0xd3,p)
    def select(m): out(6,m)
    def fill(value):
        word(0x21,0x4000);emit(0x06,value)
        loop=0xc100+len(code)
        emit(0x70,0x23,0x7c,0xfe,0xc0);word(0xc2,loop)
        emit(0x3e,value)
        for a in NEIGHBORS: word(0x32,a)
    def sample(base):
        for i,a in enumerate(SAMPLES): word(0x3a,a);word(0x32,base+i)
    out(7,0x82);select(3);fill(0x5a)
    select(mode);sample(0xc800);fill(0xa5);sample(0xc840)
    select(3);emit(0x3e,0xd3);word(0x32,0xc8ff);emit(0x76)
    assert len(code)<0x700
    return code


def command(cmd,cwd,log,env=None):
    r=subprocess.run(list(map(str,cmd)),cwd=cwd,env=env,capture_output=True,text=True,timeout=120)
    log.write_text(r.stdout+r.stderr)
    if r.returncode or 'LUA ERROR' in r.stdout+r.stderr:
        raise RuntimeError(f'failed: {log}')
    return r.stdout


def expected(a,mode,value,rom,cart):
    if mode==0 and a<0x4000: return rom[a]
    if mode in (1,2) and a>=0xd800: return rom[a-0xc000]
    if mode==2 and 0x4000<=a<0xc000: return cart[a-0x4000]
    return value


def analyze(raw,mode,rom,cart):
    assert len(raw)==65536 and raw[0xc8ff]==0xd3
    want=0x5a if mode==2 else 0xa5
    bad=[a for a in range(0x4000,0xc000) if raw[a]!=want]
    observations=[]
    for i,a in enumerate(SAMPLES):
        observations.append({'address':f'{a:04x}','before':raw[0xc800+i],
            'after':raw[0xc840+i],'backing_ram':raw[a],
            'expected_before':expected(a,mode,0x5a,rom,cart),
            'expected_after':expected(a,mode,0xa5,rom,cart)})
    return {'guest_completed':True,'window_bytes_checked':32768,
        'incorrect_backing_bytes':len(bad),'first_incorrect_address':f'{bad[0]:04x}' if bad else None,
        'adjacent_and_overlay_writes_reach_ram':all(raw[a]==0xa5 for a in NEIGHBORS),
        'read_mapping_matches':all(r['before']==r['expected_before'] and r['after']==r['expected_after'] for r in observations),
        'samples':observations}


def prom_evidence(path):
    data=path.read_bytes();assert len(data)==256
    modes={}
    for mode in range(4):
        words=[]
        for block in range(32):
            # Physical A0..A4 = BA15..BA11; A5/A6 = inverted PC0/PC1.
            index=sum(((block>>(4-i))&1)<<i for i in range(5)) | ((~mode&3)<<5)
            words.append(data[index]&15)
        modes[str(mode)]=''.join(f'{v:X}' for v in words)
    disconnected=all(int(v,16)&3==3 for v in modes['2'][8:24])
    assert disconnected
    return {'sha256':hashlib.sha256(data).hexdigest(),'mode_signatures_2k_blocks':modes,
            'mode2_internal_ram_and_rom_deselected_entire_window':disconnected}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['rom','cart','roms','source','mame','prom','output']:
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--rustc',default='rustc');a=p.parse_args()
    for n,v in vars(a).items():
        if isinstance(v,Path):setattr(a,n,v.resolve())
    a.output.mkdir(parents=True,exist_ok=False)
    common=['machines/juku/juku.c','machines/juku/juk_disk.c','machines/juku/juku_fdc.c',
            'third_party/cpu/i8080/i8080.c','common/media/media.c','common/trace/trace.c']
    command(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Imachines/juku',
             '-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace',HERE/'capture.c',*common,
             '-o',a.output/'native'],ROOT,a.output/'native-build.log')
    command([a.rustc,'--edition=2024','--crate-name','juku','--crate-type','rlib','-O',
             a.source/'core/src/lib.rs','-o',a.output/'libjuku.rlib'],ROOT,a.output/'rust-build.log')
    command([a.rustc,'--edition=2024','-O',HERE/'capture.rs','--extern',
             'juku='+str(a.output/'libjuku.rlib'),'-o',a.output/'sinijarv'],ROOT,a.output/'adapter-build.log')
    rom=a.rom.read_bytes();cart=a.cart.read_bytes();assert len(rom)==16384 and len(cart)<=32768
    report={'issue':13,'provenance':{
        'dac_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'sinijarv_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),
        'mame_version':subprocess.check_output([a.mame,'-help'],text=True).splitlines()[0],
        'rom_sha256':hashlib.sha256(rom).hexdigest(),'cart_sha256':hashlib.sha256(cart).hexdigest()},
        'physical_prom':prom_evidence(a.prom),'cases':{}}
    for kind in ['empty','cartridge','mame-stock']:
        # Stock MAME zero-fills after the cartridge. Other cases configure the
        # region explicitly for equal inputs; no emulator source is modified.
        fill=0 if kind=='mame-stock' else 255
        contents=(b'' if kind=='empty' else cart).ljust(32768,bytes([fill]))
        for mode in range(4):
            program=a.output/f'mode{mode}.bin';program.write_bytes(guest(mode))
            case={}
            for engine in (['mame'] if kind=='mame-stock' else ['native','sinijarv','mame']):
                name=f'{kind}-{mode}-{engine}';dest=a.output/name;dest.mkdir();saved=dest/'ram.bin'
                cart_arg='-' if kind=='empty' else a.cart
                env=None
                if engine=='mame':
                    env=os.environ.copy();env.update(JUKU_WINDOW_CART='stock' if kind=='mame-stock' else str(cart_arg),
                        JUKU_WINDOW_PROGRAM=str(program),JUKU_WINDOW_OUTPUT=str(saved),
                        SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
                    cmd=[a.mame,'juku','-bios','3.43m_37','-rompath',a.roms,'-video','none',
                         '-sound','none','-nothrottle','-seconds_to_run','3','-skip_gameinfo','-noreadconfig',
                         '-autoboot_delay','0','-autoboot_script',HERE/'mame.lua']
                else:cmd=[a.output/engine,a.rom,cart_arg,program,saved]
                command(cmd,dest,dest/'run.log',env)
                case[engine]=analyze(saved.read_bytes(),mode,rom,contents)
                print(name,'incorrect backing bytes:',case[engine]['incorrect_backing_bytes'],flush=True)
            report['cases'][f'{kind}-mode{mode}']=case
    (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    # Disagreements are findings, not expected failures pinned to another engine.
    for case in report['cases'].values():
        for engine,r in case.items():
            assert r['read_mapping_matches'] and r['adjacent_and_overlay_writes_reach_ram']
            if engine=='native': assert r['incorrect_backing_bytes']==0


if __name__=='__main__':main()
