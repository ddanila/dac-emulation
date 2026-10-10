#!/usr/bin/env python3
"""Bounded, optional tests using the existing TOS/M disk's real applications.
No firmware downloads, HDL or modification of input files. Each case <60 s.
"""
import argparse, subprocess, tempfile
from pathlib import Path
from robotron_boot import files, digest
p=argparse.ArgumentParser()
for name in ('rom','prom','disk'): p.add_argument(name,type=Path)
a=p.parse_args();root=Path(__file__).resolve().parents[2]
inputs=[x.resolve() for x in (a.rom,a.prom,a.disk)];before=[digest(x) for x in inputs]
original=files(inputs[2])
with tempfile.TemporaryDirectory(prefix='dac-apps-') as tmp:
    tmp=Path(tmp)
    def run(name,keys,*options):
        result=subprocess.run([root/'build/robotron-boot',*inputs,'100000000',keys,
            '--settle','64000000',*options],capture_output=True,text=True,check=True,timeout=60)
        assert 'ERROR' not in result.stdout.upper(),result.stdout
        print('PASS',name,result.stderr.strip())
        return result.stdout
    blank=tmp/'blank.img';blank.write_bytes(bytes([0xe5])*819200)
    copied=tmp/'copied.img';printer=tmp/'printer.prn'
    screen=run('two-drive PIP and printer','PIP B:=A:PIP.COM\rDIR B:\rPIP LST:=AUTOEXC.SUB\r',
        '--disk-b',blank,'--writable-b','--export-b',copied,'--printer',printer)
    assert 'B: PIP' in screen and screen.rstrip().endswith('A>'),screen
    assert files(copied)=={'PIP.COM':original['PIP.COM']}
    assert printer.read_bytes()==original['AUTOEXC.SUB'].split(b'\x1a')[0]
    ws=tmp/'wordstar.img'
    screen=run('WordStar create/save','WS DAC.TXT\rDAC WORDSTAR TEST\r\x0bD','--writable','--export',ws)
    assert 'EDITING NO FILE' in screen,screen
    content=files(ws);assert content['DAC.TXT'].split(b'\x1a')[0]==b'DAC WORDSTAR TEST\r\n'
    for name,value in original.items(): assert content[name]==value,name
    pascal=tmp/'pascal.img'
    screen=run('Turbo Pascal compile/run',"PIP DAC.PAS=CON:\rprogram DAC;\rbegin writeln('DAC COMPILED') end.\r\x1aTP\rnwDAC.PAS\rr",
        '--writable','--export',pascal)
    assert 'COMPILING' in screen and 'RUNNING' in screen and 'DAC COMPILED' in screen,screen
    content=files(pascal)
    assert content['DAC.PAS'].split(b'\x1a')[0]==b"program DAC;\rbegin writeln('DAC COMPILED') end.\r"
    for name,value in original.items(): assert content[name]==value,name
assert before==[digest(x) for x in inputs]
