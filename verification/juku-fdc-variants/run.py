#!/usr/bin/env python3
"""Investigate issue 16 using unmodified ROMs and disposable disk images."""
import argparse
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('guest', ROOT/'verification/juku-fdc/guest.py')
guest = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guest)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args, cwd, log, env=None, allow_failure=False):
    result = subprocess.run(list(map(str, args)), cwd=cwd, env=env, capture_output=True, text=True, timeout=360)
    log.write_text(result.stdout + result.stderr)
    if not allow_failure and (result.returncode or 'LUA ERROR' in log.read_text()):
        raise RuntimeError(str(log))
    return result


def fixture(path):
    # Original JMON33 loads track 0 sectors 2..10, then track 1 sectors 1..4,
    # into B800..D1FF and enters CE00 (track 1 sector 3). No CP/M required.
    disk = bytearray((i ^ (i >> 9)) & 255 for i in range(819200))
    disk[22*512:22*512+12] = bytes.fromhex('f3 3e 16 32 00 b0 3e 91 32 01 b0 76')
    path.write_bytes(disk)


def inspect_native(dest, disk, synthetic):
    prefix = dest/'capture'
    reads = list(csv.DictReader(prefix.with_suffix('.data.csv').open()))
    ram = prefix.with_suffix('.ram').read_bytes()
    raw = disk.read_bytes()
    # Single-sector boot transfers only; OS workloads can use multi-record I/O.
    result = {'data_bytes_read': len(reads), 'warm_boot_vector': ram[:8].hex(),
              'console': prefix.with_suffix('.console').read_bytes().decode('ascii', errors='replace')}
    if synthetic:
        expected = [(0,s) for s in [3,2,4,6,5,7,9,8,10]] + [(1,s) for s in [1,3,2,4]]
        actual = [(int(r['track']),int(r['sector'])) for r in reads[::512]]
        result['sector_order'] = actual
        result['bootstrap_passed'] = len(reads)==6656 and actual==expected and ram[0xb000:0xb002]==b'\x16\x91'
        for r in reads:
            offset = ((int(r['track'])*2+int(r['head']))*10+int(r['sector'])-1)*512+int(r['offset'])
            result['bootstrap_passed'] &= int(r['value'],16)==raw[offset]
        for track,sector in expected:
            source = (track*20+sector-1)*512
            target = 0xb400+track*0x1400+sector*512
            result['bootstrap_passed'] &= ram[target:target+512]==raw[source:source+512]
        assert result['bootstrap_passed'], dest
    else:
        try:
            result['file_io'] = guest.verify(raw,prefix.with_suffix('.juk').read_bytes())
            result['file_io']['guest_passed'] = 'FDC25 PASS' in result['console'] and 'FDC25 FAIL' not in result['console']
        except AssertionError:
            result['file_io'] = {'guest_passed': False}
    return result


def finish_report(output, roms):
    path=output/'results.json';report=json.loads(path.read_text())
    report['firmware_patterns']={}
    # Byte-pattern inventory, not a control-flow disassembly. Card firmware
    # also contains unrelated I/O at 1C/1D; restrict to its 30..33 FDC window.
    for name in ['ekta24','ekta31','ekta32','ekta35','ekta37','ekta43','jmon33']:
        rom=roms/(name+'.bin');b=rom.read_bytes();base=0x30 if name in ['ekta32','ekta43'] else 0x1c
        writes=[{'offset':hex(i),'port':hex(b[i+1]),'before':hex(b[i-1])}
                for i in range(1,len(b)-2) if b[i]==0xd3 and base<=b[i+1]<base+4]
        reads=[{'offset':hex(i),'port':hex(b[i+1]),'after':hex(b[i+2])}
               for i in range(1,len(b)-2) if b[i]==0xdb and base<=b[i+1]<base+4]
        report['firmware_patterns'][name]={'sha256':sha(rom),'writes':writes,'reads':reads}
    for name,result in report['cases'].items():
        dest=output/name
        result['raw_sha256']={p.name:sha(p) for p in sorted(dest.glob('capture.*')) if p.is_file()}
        result['execution_status']='failed' if result['return_code'] or result['lua_error'] else 'completed'
    report['findings']={
        'mainboard_roms':'0024 and Monitor 3.3 use inverted DAL at 1C..1F; 0031/0035/0037 use direct DAL at the same ports.',
        'card_roms':'0032/0043 use direct DAL at 30..33 in their FDC routines; polarity alone cannot provide their machine configuration.',
        'ekta24':'Native direct-bus control stalls without sector reads; inverted bus boots EKDOS 2.30 and passes guest read/write/EOF plus independent persisted-file verification in both timing modes.',
        'cross_core':'Unmodified MAME and sinijarv stall with 0024; 0037 is a successful file-I/O baseline in all three cores.',
        'monitor33':'Inverted bus transfers 13 sectors correctly and executes a synthetic bootstrap. Supplied EKDOS 2.30 has an incompatible bootstrap layout; a historical compatible OS remains unverified.',
        'mame_monitor33':'Consult the recorded process status; a failed process is not a successful FDC comparison.'
    }
    report['limitations']=[
        'FD1791 DAL polarity is verified; FD1792 single-density FM is not implemented or tested.',
        'Card ROMs 0032/0043 are inspected statically, not boot-tested; their 30..33 FDC mapping is outside this probe.',
        'JUSS contacts are supplied by capture adapters; frontend keyboard/profile selection is not added.',
        'Monitor 3.3 bootstrap passes a generated disk; the supplied EKDOS 2.30 disk does not boot under that monitor.',
        'Inversion uses the existing diagnostic option; the default remains the direct-bus FD1793 profile.',
        'Experimental paced FDC remains opt-in; these tests do not establish physical timing accuracy.'
    ]
    path.write_text(json.dumps(report,indent=2)+'\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['roms','base','source','mame','mame-roms','output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--rustc', default='rustc')
    a = parser.parse_args()
    for name,value in vars(a).items():
        if isinstance(value,Path): setattr(a,name,value.resolve())
    a.output.mkdir(parents=True,exist_ok=False)
    common = ['machines/juku/juku.c','machines/juku/juk_disk.c','machines/juku/juku_fdc.c',
              'third_party/cpu/i8080/i8080.c','common/media/media.c','common/trace/trace.c']
    for engine in ['native','paced']:
        command(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Imachines/juku',
                 '-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace',
                 '-DDAC_JUKU_EXPERIMENTAL_FDC_SYNC='+str(int(engine=='paced')),
                 HERE/'capture.c',*common,'-o',a.output/engine],ROOT,a.output/(engine+'-build.log'))
    command([a.rustc,'--edition=2024','--crate-name','juku','--crate-type','rlib','-O',
             a.source/'core/src/lib.rs','-o',a.output/'libjuku.rlib'],ROOT,a.output/'rust-core.log')
    command([a.rustc,'--edition=2024','-O',ROOT/'verification/juku-comparison/capture.rs',
             '--extern','juku='+str(a.output/'libjuku.rlib'),'-o',a.output/'sinijarv'],ROOT,a.output/'rust-adapter.log')
    disk=a.output/'file-test.juk';guest.prepare(a.base,disk)
    synthetic=a.output/'bootstrap.juk';fixture(synthetic)
    boot=a.output/'boot.keys';boot.write_text('2000 54 1\n2120 00 0\n2600 44 1\n2720 00 0\n3200 44 1\n3320 00 0\n')
    keys=a.output/'file.keys';rows=boot.read_text()
    for i,c in enumerate('fdc25\r'):
        t=16000+i*280;rows+=f'{t} {ord(c):02x} 1\n{t+120} 00 0\n'
    keys.write_text(rows)
    report={'issue':'https://github.com/infoaed/juku3000/issues/16',
            'dac_base_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'sinijarv_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),
            'sinijarv_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=a.source,text=True).strip()),
            'mame_version':subprocess.check_output([a.mame,'-help'],text=True).splitlines()[0],
            'inputs':{'base':sha(a.base)},'cases':{}}
    for name,bios in [('ekta37','3.43m_37'),('ekta24','3.42_24'),('jmon33','jmon3.3'),('jmon33-fixture','jmon3.3')]:
        rom=a.roms/(name.split('-')[0]+'.bin');report['inputs'][rom.name]=sha(rom)
        is_fixture=name.endswith('fixture');media=synthetic if is_fixture else disk
        keyfile=boot if name.startswith('jmon33') else keys
        end=30000 if name.startswith('jmon33') else 90000
        engines=['native-inverted','paced-inverted'] if is_fixture else ['native-direct','native-inverted','sinijarv','mame']
        if name=='ekta24':engines+=['paced-inverted']
        for engine in engines:
            dest=a.output/(name+'-'+engine);dest.mkdir();prefix=dest/'capture'
            env=os.environ.copy();env.pop('JUKU_JUSS_CONTACTS',None);env.pop('JUKU_FDC_BUS_INVERT',None)
            if name=='ekta24':env['JUKU_JUSS_CONTACTS']='1'
            if engine.endswith('inverted'):env['JUKU_FDC_BUS_INVERT']='1'
            if engine=='mame':
                shutil.copyfile(media,dest/'media.juk')
                env.update(JUKU_VARIANT_SCHEDULER=str(ROOT/'verification/juku-scroll/mame.lua'),
                           JUKU_SCROLL_PREFIX=str(prefix),JUKU_SCROLL_KEYS=str(keyfile),JUKU_SCROLL_FROM=str(end/1000-1),
                           SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
                cmd=[a.mame,'juku','-bios',bios,'-rompath',a.mame_roms,'-flop1',dest/'media.juk',
                     '-video','none','-sound','none','-nothrottle','-seconds_to_run',str(end//1000),
                     '-skip_gameinfo','-noreadconfig','-autoboot_delay','0','-autoboot_script',HERE/'mame.lua']
            else:
                executable=engine.split('-')[0]
                cmd=[a.output/executable,rom,media,prefix,keyfile,str(end),str(end-1000)]
            run=command(cmd,dest,dest/'run.log',env,allow_failure=True)
            result={'return_code':run.returncode,'juss_contacts':name=='ekta24',
                    'inverted_bus':engine.endswith('inverted'),'log_sha256':sha(dest/'run.log'), 'lua_error':'LUA ERROR' in run.stdout+run.stderr}
            if not run.returncode and 'LUA ERROR' not in run.stdout+run.stderr:
                events=list(csv.DictReader(prefix.with_suffix('.events.csv').open()))
                assert sum(r['kind']=='KEY' for r in events)==len(keyfile.read_text().splitlines()),dest
                samples=list(csv.DictReader(prefix.with_suffix('.samples.csv').open()))
                result['final_pc']=samples[-1]['pc']
                if engine.startswith(('native','paced')):
                    result.update(inspect_native(dest,media,is_fixture))
                    if (name=='ekta24' and engine.endswith('inverted')) or (name=='ekta37' and engine=='native-direct'):
                        assert result['file_io']['guest_passed'],dest
                else:
                    if engine=='sinijarv':result['data_io_waits']=int(re.search(r'data_io_waits=(\d+)',run.stdout)[1])
                    saved=dest/('media.juk' if engine=='mame' else 'capture.juk')
                    try: result['persisted_file']=guest.verify(media.read_bytes(),saved.read_bytes())
                    except AssertionError:result['persisted_file']=None
            report['cases'][dest.name]=result
            (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
            print(dest.name, result, flush=True)
    finish_report(a.output,a.roms)


if __name__=='__main__':main()
