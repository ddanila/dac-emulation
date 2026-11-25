#!/usr/bin/env python3
"""Opt-in issue #23 media/BDOS comparison. External inputs remain unchanged."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('comparison', ROOT/'verification/juku-comparison/run.py')
cmp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cmp)
SKEW = (0, 2, 4, 6, 8, 1, 3, 5, 7, 9)
BLOCKS = (96, 97, 98, 196)


def linear(raw):
    """EKDOS logical track/sector order, including its reserved tracks."""
    if len(raw) != 819200:
        raise ValueError('requires DS/DD 819200-byte JUK')
    return b''.join(raw[((t % 80)*2+t//80)*5120+s*512:
                       ((t % 80)*2+t//80)*5120+(s+1)*512]
                    for t in range(160) for s in SKEW)


def physical(data):
    if len(data) != 819200:
        raise ValueError('requires 819200 bytes')
    raw = bytearray(len(data))
    for t in range(160):
        for i, s in enumerate(SKEW):
            off = ((t % 80)*2+t//80)*5120+s*512
            raw[off:off+512] = data[t*5120+i*512:t*5120+(i+1)*512]
    return bytes(raw)


def payload(changed=False):
    return b''.join(bytes([r ^ (128 if changed else 0)])+bytes(range(1,128))
                    for r in range(128))


def program():
    code=bytearray(); labels={}; refs=[]
    def emit(*v): code.extend(v)
    def label(n): labels[n]=0x100+len(code)
    def addr(op,n): emit(op);refs.append((len(code),n));emit(0,0)
    def bdos(fn,n=None):
        if n: addr(0x11,n)
        emit(0x0e,fn,0xcd,5,0)
    def check(): emit(0xb7);addr(0xc2,'fail')
    emit(0x31,0,0x30)  # private stack at 3000h
    bdos(15,'fcb');emit(0xfe,0xff);addr(0xca,'fail')
    bdos(26,'buffer')
    label('read');bdos(20,'fcb');check()
    addr(0x21,'buffer');addr(0x3a,'record');emit(0xbe);addr(0xc2,'fail')
    emit(0x23,0x3e,1)
    label('compare');emit(0xbe);addr(0xc2,'fail');emit(0x23,0x3c,0xfe,128);addr(0xc2,'compare')
    addr(0x3a,'record');emit(0x3c);addr(0x32,'record');emit(0xfe,128);addr(0xc2,'read')
    bdos(20,'fcb');emit(0xfe,1);addr(0xc2,'fail')
    bdos(16,'fcb')
    addr(0x21,'tail');emit(0x06,24,0xaf)
    label('clear');emit(0x77,0x23,0x05);addr(0xc2,'clear')
    bdos(15,'fcb');emit(0xfe,0xff);addr(0xca,'fail')
    emit(0xaf);addr(0x32,'record')
    label('write');addr(0x3a,'record');emit(0xee,128);addr(0x32,'buffer')
    bdos(21,'fcb');check()
    addr(0x3a,'record');emit(0x3c);addr(0x32,'record');emit(0xfe,128);addr(0xc2,'write')
    bdos(16,'fcb');emit(0xfe,0xff);addr(0xca,'fail')
    bdos(9,'pass');emit(0xc3,0,0)
    label('fail');bdos(9,'error');emit(0xc3,0,0)
    label('pass');code.extend(b'\r\nLAYOUT23 PASS\r\n$')
    label('error');code.extend(b'\r\nLAYOUT23 FAIL\r\n$')
    label('fcb');code.extend(b'\0LAYOUT23DAT')
    label('tail');code.extend(bytes(24))
    label('record');emit(0)
    label('buffer');code.extend(bytes(128))
    for off,n in refs: code[off:off+2]=labels[n].to_bytes(2,'little')
    return code


def prepare(base):
    data=bytearray(linear(base))
    data[10240:14336]=b'\xe5'*4096
    code=program()
    for slot,name,blocks,count in [(0,b'LAYOUT23COM',(1,),(len(code)+127)//128),
                                   (1,b'LAYOUT23DAT',BLOCKS,128)]:
        e=bytearray(32);e[1:12]=name;e[15]=count;e[16:16+len(blocks)]=bytes(blocks)
        data[10240+slot*32:10272+slot*32]=e
    data[14336:14336+len(code)]=code
    content=payload()
    for i,b in enumerate(BLOCKS):
        data[10240+b*4096:10240+(b+1)*4096]=content[i*4096:(i+1)*4096]
    return physical(data)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['base','rom','roms','source','mame','output']:
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--rustc',default='rustc')
    a=p.parse_args()
    for n,v in vars(a).items():
        if isinstance(v,Path): setattr(a,n,v.resolve())
    a.output.mkdir(parents=True,exist_ok=False)
    raw=a.base.read_bytes(); converted=linear(raw)
    assert physical(converted)==raw
    disk=a.output/'input.juk';disk.write_bytes(prepare(raw))
    keys=a.output/'input.keys';cmp.keys(keys,'layout23\r')
    common=['machines/juku/juku.c','machines/juku/juk_disk.c','machines/juku/juku_fdc.c',
            'third_party/cpu/i8080/i8080.c','common/media/media.c','common/trace/trace.c']
    cmp.command(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Imachines/juku',
                 '-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace',
                 'verification/juku-feditor/capture.c',*common,'-o',a.output/'native'],
                 ROOT,a.output/'native-build.log')
    cmp.command([a.rustc,'--edition=2024','--crate-name','juku','--crate-type','rlib','-O',
                 a.source/'core/src/lib.rs','-o',a.output/'libjuku.rlib'],ROOT,a.output/'rust-build.log')
    cmp.command([a.rustc,'--edition=2024','-O',ROOT/'verification/juku-comparison/capture.rs',
                 '--extern','juku='+str(a.output/'libjuku.rlib'),'-o',a.output/'sinijarv'],
                 ROOT,a.output/'adapter-build.log')
    # Explicit linear definition: conversion has already removed skew/head ordering.
    (a.output/'diskdefs').write_text('diskdef linear\n seclen 128\n tracks 160\n sectrk 40\n blocksize 4096\n skew 1\n boottrk 2\n maxdir 128\n os 2.2\nend\n')
    (a.output/'historical.cpm').write_bytes(converted)
    listing=cmp.command(['cpmls','-f','linear','historical.cpm'],a.output,a.output/'cpmls.log')
    (a.output/'diagnostic.cpm').write_bytes(linear(disk.read_bytes()))
    cmp.command(['cpmcp','-f','linear','diagnostic.cpm','0:layout23.dat','extracted.dat'],
                a.output,a.output/'cpmcp.log')
    assert (a.output/'extracted.dat').read_bytes()==payload()
    # Negative control: the same raw bytes are not a linear CP/M image.
    wrong=subprocess.run(['cpmcp','-f','linear','input.juk','0:layout23.dat','wrong.dat'],
                         cwd=a.output,capture_output=True,text=True)
    wrong_matches=(wrong.returncode==0 and (a.output/'wrong.dat').exists()
                   and (a.output/'wrong.dat').read_bytes()==payload())
    assert not wrong_matches
    report={'issue':23,'provenance':{
        'dac_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'sinijarv_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),
        'mame_version':subprocess.check_output([a.mame,'-help'],text=True).splitlines()[0],
        'base_sha256':hashlib.sha256(raw).hexdigest(),
        'rom_sha256':hashlib.sha256(a.rom.read_bytes()).hexdigest()},
        'round_trip_all_bytes':True,'cpmtools_extracted_pattern':True,
        'raw_as_linear_negative_control':{'exit_code':wrong.returncode,
                                         'file_created':(a.output/'wrong.dat').exists(),
                                         'matches_expected_file':wrong_matches},
        'historical_listing':listing.splitlines(),'blocks':BLOCKS,'engines':{}}
    before=linear(disk.read_bytes())
    for engine in ['native','mame','sinijarv']:
        dest=a.output/(engine+'-run');dest.mkdir();prefix=dest/'capture';env=None
        if engine=='mame':
            saved=dest/'media.juk';shutil.copyfile(disk,saved)
            env=os.environ.copy();env.update(JUKU_COMPARISON_SCHEDULER=str(ROOT/'verification/juku-scroll/mame.lua'),
                JUKU_SCROLL_PREFIX=str(prefix),JUKU_SCROLL_KEYS=str(keys),JUKU_SCROLL_FROM='89',
                SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
            cmd=[a.mame,'juku','-bios','3.43m_37','-rompath',a.roms,'-flop1',saved,'-video','none',
                 '-sound','none','-nothrottle','-seconds_to_run','90','-skip_gameinfo','-noreadconfig',
                 '-autoboot_delay','0','-autoboot_script',ROOT/'verification/juku-comparison/mame.lua']
        else:
            saved=dest/'capture.juk'
            cmd=[a.output/engine,a.rom,disk,prefix,keys,'90000','89000']
        cmp.command(cmd,dest,dest/'run.log',env)
        events=list(csv.DictReader((dest/'capture.events.csv').open()))
        assert sum(e['kind']=='KEY' for e in events)==len(keys.read_text().splitlines())
        final,path=cmp.fed.image_at(cmp.fed.frames(dest,engine),1e6)
        rows=cmp.analysis.text_rows(cmp.analysis.pixels(path),cmp.analysis.font_table(a.rom.read_bytes()))
        after=linear(saved.read_bytes())
        content=b''.join(after[10240+b*4096:10240+(b+1)*4096] for b in BLOCKS)
        allowed=set(range(10240,14336))
        for b in BLOCKS: allowed.update(range(10240+b*4096,10240+(b+1)*4096))
        result={'guest_pass':'LAYOUT23 PASS' in rows,'rewritten_bytes_correct':content==payload(True),
                'unrelated_bytes_unchanged':all(x==y or i in allowed for i,(x,y) in enumerate(zip(before,after))),
                'final_text':rows}
        report['engines'][engine]=result
        print(engine,result,flush=True)
    (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    assert all(r['guest_pass'] and r['rewritten_bytes_correct'] and r['unrelated_bytes_unchanged']
               for r in report['engines'].values())


if __name__=='__main__': main()
