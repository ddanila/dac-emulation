#!/usr/bin/env python3
"""Replay Juku issue workloads across independent cores; keep failures as findings."""
import argparse
import csv
import importlib.util
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'verification/juku-scroll'))


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


fed = module('fed', 'verification/juku-feditor/run.py')
fonts = module('fonts', 'verification/juku-fonts/run.py')
scroll = module('scroll', 'verification/juku-scroll/run.py')
analysis = module('analysis', 'verification/juku-scroll/analyze.py')
fdc = module('guest', 'verification/juku-fdc/guest.py')


def command(cmd, cwd, log, env=None, runtime=False):
    r = subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, capture_output=True, text=True, timeout=360)
    log.write_text(r.stdout + r.stderr)
    if runtime:
        return r
    if r.returncode or 'LUA ERROR' in r.stdout + r.stderr:
        raise RuntimeError(f'runner failed: {log}')
    return r.stdout


def keys(path, text):
    rows = []
    for t, word in [(2000, 'TDD'), (16000, text)]:
        for c in word:
            rows.extend([(t, ord(c), 1), (t+120, 0, 0)])
            t += 280
    path.write_text(''.join(f'{t} {k:02x} {d}\n' for t, k, d in rows))


def inspect(case, engine, dest, disk, rom):
    index = fed.frames(dest, engine)
    assert index, 'no frames captured'
    final, frame_path = fed.image_at(index, 1e6)
    result = {'execution_status': 'completed', 'dimensions': list(final.size), 'frame_sha256': fed.sha(frame_path)}
    samples = list(csv.DictReader((dest / 'capture.samples.csv').open()))
    result['final_pc'] = samples[-1]['pc']
    if final.size == (320, 241):
        result['final_text'] = analysis.text_rows(analysis.pixels(frame_path), analysis.font_table(rom.read_bytes()))
    physical = dest / ('capture.physical.ram' if engine == 'mame' else 'capture.ram')
    ram = physical.read_bytes()
    result['scroll_flag'] = ram[0xd499]
    result['parsed_drive'] = ram[0xbbf0]
    if engine == 'sinijarv':
        log = (dest / 'run.log').read_text()
        result['data_io_wait_instructions'] = int(re.search(r'data_io_waits=(\d+)', log)[1])
        result['longest_data_io_instruction_cycles'] = int(re.search(r'longest_instruction=(\d+)', log)[1])
    if case.startswith(('ekdos-', 'monitor-')):
        result['invalid_drive_value_observed_at_end'] = ram[0xbbf0] >= 3
        result['scroll_flags_sampled'] = sorted({r['scroll_flag'] for r in samples if 'scroll_flag' in r})

    if case.startswith('feditor'):
        editor, _ = fed.image_at(index, 86)
        result['editor_dimensions'] = list(editor.size)
        if editor.width >= 80 and editor.height > 112:
            grid = sum((editor.getpixel((18+8*i,112)) != 0) << (7-i) for i in range(8))
            result['space_grid_first_row'] = grid
            result['font_address_prediction_matches'] = grid & 127 == (0 if case.endswith('control') else 0x6d)
        intervals = []
        for start, end in fed.blank_intervals(dest, engine):
            if end-start < .12:
                continue
            image, _ = fed.image_at(index, (start+end)/2)
            intervals.append({'start': start, 'end': end, 'dimensions': list(image.size),
                              'lit_pixels': sum(x != 0 for x in image.getdata())})
        result['blanking'] = intervals
        result['blanking_honored_at_samples'] = bool(intervals) and all(i['lit_pixels'] == 0 for i in intervals)
        saved = dest / ('media.juk' if engine == 'mame' else 'capture.juk')
        try:
            actual = fonts.extract(saved, b'TEST    LAT')
            expected = fonts.extract(disk, b'FEDITOR LAT')
            result['font_file'] = {'bytes': len(actual), 'first_byte': actual[0],
                'matches_except_first_pixel': len(actual) == len(expected) and actual[1:] == expected[1:]
                    and actual[0] & 127 == expected[0] & 127}
        except ValueError:
            result['font_file'] = {'matches_except_first_pixel': False, 'reason': 'saved file absent or invalid'}

    if case in ('mfd', 'bowling'):
        ptr = 0x09fe if case == 'mfd' else 0x7000
        font = ram[ptr:ptr+864]
        result['space_glyph'] = font[:9].hex()
        result['dd01_space_corruption_reproduced'] = font[:9] == b'\xff'+bytes(8)
        result['installed_font_pointer'] = int.from_bytes(ram[0xd7fb:0xd7fd], 'little')
        expected = bytes(v | (v >> 1) for v in rom.read_bytes()[0x1d01:0x1d01+864])
        exempt = range(18,36) if case == 'bowling' else ()
        result['font_matches_dd01_transform'] = all(v == expected[i] for i,v in enumerate(font) if i not in exempt)

    if case == 'scroll-diagnostic':
        paths = [p for _, p in index]
        if all(Image.open(p).size == (320,241) for p in paths):
            result['scroll'] = analysis.scroll_frames(paths, analysis.font_table(rom.read_bytes()))
        else:
            result['scroll'] = {'completed': False, 'reason': 'unexpected frame geometry'}
    if case == 'fdc25':
        saved = dest / ('media.juk' if engine == 'mame' else 'capture.juk')
        try:
            result['file_io'] = fdc.verify(disk.read_bytes(), saved.read_bytes())
            rows = result.get('final_text', [])
            passed = 'FDC25 PASS' in rows
            returned = passed and any(row.startswith('A>') for row in rows[rows.index('FDC25 PASS')+1:])
            result['file_io']['returned_prompt'] = returned
            result['file_io']['passed'] = passed and returned
        except AssertionError:
            result['file_io'] = {'passed': False, 'reason': 'persisted file or unrelated-byte verification failed'}
    return result


def monitor_repeats(a):
    """Keep intermittent process failures and successful geometry side by side."""
    runs = []
    for adapter in [False, True]:
        for attempt in range(3):
            dest = a.output / ('monitor33-repeat-' + str(int(adapter)) + '-' + str(attempt))
            dest.mkdir()
            media = dest / 'media.juk'
            shutil.copyfile(a.base, media)
            env = os.environ.copy()
            env.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
                       JUKU_COMPARISON_SCHEDULER=str(ROOT/'verification/juku-scroll/mame.lua'),
                       JUKU_SCROLL_PREFIX=str(dest/'capture'),
                       JUKU_SCROLL_KEYS=str(a.output/'monitor33/input.keys'), JUKU_SCROLL_FROM='3')
            cmd = [a.mame,'juku','-bios','jmon3.3','-rompath',a.roms,'-flop1',media,
                   '-video','none','-sound','none','-nothrottle','-seconds_to_run','5',
                   '-skip_gameinfo','-noreadconfig']
            if adapter:
                cmd += ['-autoboot_delay','0','-autoboot_script',HERE/'mame.lua']
            r = command(cmd, dest, dest/'run.log', env, runtime=True)
            result = {'capture_adapter': adapter, 'attempt': attempt+1, 'return_code': r.returncode,
                      'lua_error': 'LUA ERROR' in r.stdout+r.stderr,
                      'log_sha256': fed.sha(dest/'run.log')}
            if adapter and r.returncode == 0 and not result['lua_error']:
                image, _ = fed.image_at(fed.frames(dest,'mame'),1e6)
                result['dimensions'] = list(image.size)
            runs.append(result)
    return runs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ['source','rom','monitor33','base','mfd','bowling','archive','mame','roms','output']:
        p.add_argument('--'+arg, type=Path, required=True)
    p.add_argument('--rustc', default='rustc')
    p.add_argument('--case', action='append', help='run only this named workload; repeat to select more')
    p.add_argument('--analyze-only', action='store_true', help='re-read captures in an existing output directory')
    a = p.parse_args()
    for k,v in vars(a).items():
        if isinstance(v,Path): setattr(a,k,v.resolve())
    if a.analyze_only:
        report = json.loads((a.output/'results.json').read_text())
        for name, engines in report['cases'].items():
            rom = a.monitor33 if name == 'monitor33' else a.rom
            disk = a.output/name/'input.juk'
            if not disk.exists(): disk = a.base
            for engine in engines:
                if engines[engine].get('execution_status') == 'failed': continue
                engines[engine] = inspect(name, engine, a.output/name/engine, disk, rom)
                print(name, engine, 'analyzed', flush=True)
        (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
        contact_sheet(a.output)
        return
    a.output.mkdir(parents=True,exist_ok=False)
    # The third-party core has no library dependencies. Compile its unmodified
    # source directly, avoiding GUI/workspace dependencies and release packaging.
    command([a.rustc,'--edition=2024','--crate-name','juku','--crate-type','rlib','-O',
             a.source/'core/src/lib.rs','-o',a.output/'libjuku.rlib'],ROOT,a.output/'rust-core.log')
    command([a.rustc,'--edition=2024','-O',HERE/'capture.rs','--extern',
             'juku='+str(a.output/'libjuku.rlib'),'-o',a.output/'sinijarv'],ROOT,a.output/'rust-adapter.log')
    common = ['machines/juku/juku.c','machines/juku/juk_disk.c','machines/juku/juku_fdc.c',
              'third_party/cpu/i8080/i8080.c','common/media/media.c','common/trace/trace.c']
    for engine in ['native','paced']:
        command(['cc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Imachines/juku',
                 '-Ithird_party/cpu/i8080','-Icommon/media','-Icommon/trace',
                 '-DDAC_JUKU_EXPERIMENTAL_FDC_SYNC='+str(int(engine=='paced')),
                 'verification/juku-feditor/capture.c',*common,'-o',a.output/engine],ROOT,a.output/(engine+'-build.log'))
    cases = []
    for control in [False,True]:
        name = 'feditor-control' if control else 'feditor-original'
        dest=a.output/name;dest.mkdir();disk=dest/'input.juk'
        fed.media(a.base,a.archive,disk,control);fed.schedule(dest/'input.keys')
        cases.append((name,a.rom,disk,152000,18000))
    for name in ['mfd','bowling']:
        dest=a.output/name;dest.mkdir();disk=dest/'input.juk'
        filename=name.upper().encode().ljust(8)+b'COM'
        fonts.insert(a.base,disk,filename,fonts.extract(getattr(a,name),filename))
        keys(dest/'input.keys',name+'\r');cases.append((name,a.rom,disk,30000,18000))
    for context, seqname in [('ekdos','plain'),('ekdos','colon'),('ekdos','semicolon'),('ekdos','colon-q'),
                              ('monitor','colon'),('monitor','semicolon'),('diagnostic','plain')]:
        name='scroll-diagnostic' if context=='diagnostic' else context+'-'+seqname
        dest=a.output/name;dest.mkdir();disk=a.base
        sequence='scroll\r' if context=='diagnostic' else scroll.SEQUENCES[seqname]
        rows,end,start=scroll.schedule(context,sequence)
        (dest/'input.keys').write_text(''.join(f'{t} {k:02x} {d}\n' for t,k,d in rows))
        if context=='diagnostic':
            disk=dest/'input.juk';scroll.prepare(a.base,disk)
        cases.append((name,a.rom,disk,end,start))
    dest=a.output/'fdc25';dest.mkdir();disk=dest/'input.juk';fdc.prepare(a.base,disk)
    keys(dest/'input.keys','fdc25\r');cases.append(('fdc25',a.rom,disk,90000,18000))
    dest=a.output/'monitor33';dest.mkdir();(dest/'input.keys').write_text('')
    cases.append(('monitor33',a.monitor33,a.base,5000,3000))
    if a.case:
        unknown = set(a.case)-{c[0] for c in cases}
        if unknown: raise ValueError('unknown cases: '+', '.join(sorted(unknown)))
        cases = [c for c in cases if c[0] in a.case]
    report={'source_url':'https://github.com/sinijarv-juku/juku-emu',
            'source_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.source,text=True).strip(),
            'source_dirty':bool(subprocess.check_output(['git','status','--porcelain'],cwd=a.source,text=True).strip()),
            'dac_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'mame_version':subprocess.check_output([a.mame,'-help'],text=True).splitlines()[0],
            'rustc':subprocess.check_output([a.rustc,'--version'],text=True).strip(),
            'inputs':{k:fed.sha(getattr(a,k)) for k in ['rom','monitor33','base','mfd','bowling','archive']},
            'cases':{}}
    for name,rom,disk,end,start in cases:
        results={}
        for engine in ['native','mame','sinijarv']+(['paced'] if name=='fdc25' else []):
            dest=a.output/name/engine;dest.mkdir();prefix=dest/'capture';keyfile=a.output/name/'input.keys'
            if engine=='mame':
                media=dest/'media.juk';shutil.copyfile(disk,media)
                env=os.environ.copy();env.update(JUKU_COMPARISON_SCHEDULER=str(ROOT/'verification/juku-scroll/mame.lua'),
                    JUKU_SCROLL_PREFIX=str(prefix),JUKU_SCROLL_KEYS=str(keyfile),JUKU_SCROLL_FROM=str(start/1000),
                    SDL_VIDEODRIVER='dummy',SDL_AUDIODRIVER='dummy')
                cmd=[a.mame,'juku','-bios','jmon3.3' if name=='monitor33' else '3.43m_37','-rompath',a.roms,
                     '-flop1',media,'-video','none','-sound','none','-nothrottle','-seconds_to_run',str((end+999)//1000),
                     '-skip_gameinfo','-noreadconfig','-autoboot_delay','0','-autoboot_script',HERE/'mame.lua']
            else:
                env=None;cmd=[a.output/engine,rom,disk,prefix,keyfile,str(end),str(start)]
            run = command(cmd,dest,dest/'run.log',env,runtime=True)
            if run.returncode or 'LUA ERROR' in run.stdout + run.stderr:
                results[engine] = {'execution_status': 'failed', 'return_code': run.returncode,
                                   'log_sha256': fed.sha(dest/'run.log'),
                                   'reason': 'Emulator process failed; no successful shutdown capture.'}
                if name == 'monitor33' and engine == 'mame':
                    bare = command(cmd[:-4], dest, dest/'without-adapter.log', env, runtime=True)
                    results[engine]['without_capture_script_return_code'] = bare.returncode
                print(name, engine, 'FAILED', run.returncode, flush=True)
                continue
            events=list(csv.DictReader((dest/'capture.events.csv').open()))
            assert sum(e['kind']=='KEY' for e in events)==len(keyfile.read_text().splitlines())
            results[engine]=inspect(name,engine,dest,disk,rom)
            print(name,engine,'captured',flush=True)
        report['cases'][name]=results
        (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    if 'monitor33' in report['cases']:
        report['monitor33_mame_repeats'] = monitor_repeats(a)
        (a.output/'results.json').write_text(json.dumps(report,indent=2)+'\n')
    contact_sheet(a.output)


def contact_sheet(output):
    sheet=Image.new('RGB',(960,3*270),'#444');draw=ImageDraw.Draw(sheet)
    for row,(case,t) in enumerate([('feditor-original',45),('feditor-original',86),('feditor-control',86)]):
        for col,engine in enumerate(['native','mame','sinijarv']):
            if not (output/case/engine/'capture.ram').exists():
                draw.text((320*col+3,270*row+3), engine+' / capture failed', fill='white')
                continue
            im,_=fed.image_at(fed.frames(output/case/engine,engine),t)
            sheet.paste(im,(320*col,270*row+20));draw.text((320*col+3,270*row+3),engine+' / '+case,fill='white')
    sheet.save(output/'comparison.png')


if __name__=='__main__':main()
