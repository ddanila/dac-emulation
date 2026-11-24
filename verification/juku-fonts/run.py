#!/usr/bin/env python3
"""Compare real applications and an explicitly labelled font-address control."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/juku-scroll'))
from prepare import physical


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def entries(raw):
    if len(raw) != 819200:
        raise ValueError('requires EKDOS DS/DD 819200-byte images')
    return [bytes(raw[physical(10240 + i * 32 + j)] for j in range(32)) for i in range(128)]


def extract(path, name):
    raw = path.read_bytes()
    found = [e for e in entries(raw) if e[0] == 0 and e[1:12] == name]
    if len(found) != 1 or found[0][12] != 0 or found[0][14] != 0:
        raise ValueError('requires one unambiguous, single-extent application')
    e = found[0]
    blocks = list(filter(None, e[16:]))
    if not blocks or max(blocks) >= 197 or len(blocks) * 4096 < e[15] * 128:
        raise ValueError('invalid allocation')
    return b''.join(bytes(raw[physical(10240 + b * 4096 + i)] for i in range(4096))
                    for b in blocks)[:e[15] * 128]


def insert(base, path, name, program):
    raw = bytearray(base.read_bytes())
    es = entries(raw)
    if any(e[0] < 16 and e[1:12] == name for e in es):
        raise ValueError('application already exists on base disk')
    if not 0 < len(program) <= 4096:
        raise ValueError('requires a single-block application')
    used = {0}
    for e in es:
        if e[0] < 16:
            used.update(e[16:])
    block = next(b for b in range(1, 197) if b not in used)
    slot = next(i for i, e in enumerate(es) if e[0] == 0xe5)
    entry = bytearray(32)
    entry[1:12] = name
    entry[15] = (len(program) + 127) // 128
    entry[16] = block
    for i, v in enumerate(entry):
        raw[physical(10240 + slot * 32 + i)] = v
    for i, v in enumerate(program.ljust(4096, b'\0')):
        raw[physical(10240 + block * 4096 + i)] = v
    path.write_bytes(raw)
    return {'directory_slot': slot, 'block': block, 'program_bytes': len(program)}


def command(cmd, cwd, log, env=None):
    r = subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, capture_output=True, text=True, timeout=240)
    log.write_text(r.stdout + r.stderr)
    if r.returncode or 'LUA ERROR' in r.stdout + r.stderr:
        raise RuntimeError(f'failed: {log}')
    return r.stdout


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['rom', 'base', 'bowling', 'mfd', 'roms', 'mame', 'output']:
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    for name, value in vars(a).items():
        setattr(a, name, value.resolve())
    a.output.mkdir(parents=True, exist_ok=False)
    core = ['machines/juku/juku.c', 'machines/juku/juk_disk.c', 'machines/juku/juku_fdc.c',
            'third_party/cpu/i8080/i8080.c', 'common/media/media.c', 'common/trace/trace.c']
    flags = ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Imachines/juku',
             '-Ithird_party/cpu/i8080', '-Icommon/media', '-Icommon/trace']
    for engine in ['native', 'paced']:
        command(['cc', *flags, '-DDAC_JUKU_EXPERIMENTAL_FDC_SYNC=' + str(int(engine == 'paced')),
                 'verification/juku-fonts/capture.c', *core, '-o', a.output / engine], ROOT,
                a.output / (engine + '-build.log'))
    report = {'issue': 'https://github.com/infoaed/juku3000/issues/19',
              'core_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'mame_version': subprocess.check_output([a.mame, '-help'], text=True).splitlines()[0],
              'inputs': {k: {'path': str(getattr(a, k)), 'sha256': digest(getattr(a, k))}
                         for k in ['rom', 'base', 'bowling', 'mfd']}, 'cases': {}}
    rom = a.rom.read_bytes()
    sheet = Image.new('RGB', (960, 4 * 270), '#555555')
    draw = ImageDraw.Draw(sheet)
    for app, pointer, operand in [('mfd', 0x09fe, 0x0142), ('bowling', 0x7000, 0x0b44)]:
        name = app.upper().encode().ljust(8) + b'COM'
        program = extract(getattr(a, app), name)
        for control in [False, True]:
            case = app + ('-control' if control else '-original')
            directory = a.output / case
            directory.mkdir()
            media = directory / 'media.juk'
            preparation = insert(a.base, media, name, program)
            media.chmod(0o444)
            rows = []
            for t, text in [(2000, 'TDD'), (16000, app + '\r')]:
                for c in text:
                    rows += [(t, ord(c), 1), (t + 120, 0, 0)]
                    t += 280
            keys = directory / 'input.keys'
            keys.write_text(''.join(f'{t} {k:02x} {d}\n' for t, k, d in rows))
            engines = {}
            fonts = []
            frames = []
            for engine in ['native', 'paced', 'mame']:
                dest = directory / engine
                dest.mkdir()
                prefix = dest / 'capture'
                env = os.environ.copy()
                if engine != 'mame':
                    cmd = [a.output / engine, a.rom, media, keys, prefix, '30000', str(int(control))]
                else:
                    env.update(JUKU_FONT_SCHEDULER=str(ROOT / 'verification/juku-scroll/mame.lua'),
                               JUKU_FONT_OPERAND=str(operand if control else 0),
                               JUKU_SCROLL_PREFIX=str(prefix), JUKU_SCROLL_KEYS=str(keys),
                               JUKU_SCROLL_FROM='29.9', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
                    cmd = [a.mame, 'juku', '-bios', '3.43m_37', '-rompath', a.roms, '-flop1', media,
                           '-video', 'none', '-sound', 'none', '-nothrottle', '-seconds_to_run', '30',
                           '-skip_gameinfo', '-noreadconfig', '-autoboot_delay', '0', '-autoboot_script',
                           ROOT / 'verification/juku-fonts/mame.lua']
                stdout = command(cmd, dest, dest / 'run.log', env)
                trace = prefix.with_suffix('.trace.csv').read_text().splitlines()
                patches = sum(x.startswith('PATCH,') for x in trace)
                if patches != int(control):
                    raise AssertionError(f'{case}/{engine}: control did not execute correctly')
                raw = prefix.with_suffix('.physical.ram' if engine == 'mame' else '.ram').read_bytes()
                if int.from_bytes(raw[0xd7fb:0xd7fd], 'little') != pointer:
                    raise AssertionError('application did not install its font')
                font = raw[pointer:pointer + 864]
                source = 0x1d02 if control else 0x1d01
                expected = bytes(v | (v >> 1) for v in rom[source:source + 864])
                exempt = range(18, 36) if app == 'bowling' else ()  # two application-supplied glyphs
                assert all(v == expected[i] for i, v in enumerate(font) if i not in exempt)
                assert font[:9] == (bytes(9) if control else b'\xff' + bytes(8))
                # MAME's shutdown CPU-visible dump can also trigger read taps.
                # Restrict evidence to the application's two font-copy reads.
                reads = [x.split(',') for x in trace if x.startswith('READ,') and
                         int(x.split(',')[4], 16) in (operand + 10, operand + 11)]
                assert len(reads) == 1728
                assert all(int(row[2], 16) == source + 0xc000 + i // 2 and
                           int(row[3], 16) == rom[source + i // 2]
                           for i, row in enumerate(reads))
                # Monitor initialization must establish the correct DD02 pointer.
                assert any(x.startswith('FONT,') and ',d7fb,02,dcb4' in x for x in trace)
                if engine == 'mame':
                    events = prefix.with_suffix('.events.csv').read_text().splitlines()
                    assert sum(x.startswith('KEY,') for x in events) == len(rows)
                    frame_path = sorted(dest.glob('capture-*.png'))[-1]
                else:
                    assert f'keys={len(rows)} ' in stdout
                    frame_path = prefix.with_suffix('.pbm')
                im = Image.open(frame_path).convert('RGB')
                assert im.size == (320, 241)
                frames.append(im.convert('1'))
                row = (0 if app == 'mfd' else 2) + int(control)
                col = ['native', 'paced', 'mame'].index(engine)
                sheet.paste(im, (col * 320, row * 270 + 25))
                draw.text((col * 320 + 4, row * 270 + 4), f'{case} / {engine}', fill='white')
                engines[engine] = {'installed_font': hex(pointer), 'font_bytes': len(font),
                    'font_matches_source_transform': True, 'space_glyph': font[:9].hex(),
                    'source_reads': len(reads), 'first_source_address': reads[0][2], 'patches': patches,
                    'keys': len(rows), 'frame_sha256': digest(frame_path),
                    'trace_sha256': digest(prefix.with_suffix('.trace.csv')),
                    'physical_ram_sha256': hashlib.sha256(raw).hexdigest()}
                fonts.append(font)
                print(case, engine, 'verified', flush=True)
            assert fonts[0] == fonts[1] == fonts[2]
            differences = {}
            for index, engine in [(1, 'paced'), (2, 'mame')]:
                difference = ImageChops.difference(frames[0], frames[index])
                differences[engine] = {'pixels': sum(bool(v) for v in difference.getdata()),
                                       'bounds': difference.getbbox()}
                # Only the blinking input cursor may differ on these idle screens.
                allowed = Image.new('1', (320, 241))
                if app == 'bowling':
                    ImageDraw.Draw(allowed).rectangle((240, 150, 247, 159), fill=255)
                assert ImageChops.subtract(difference, allowed).getbbox() is None
            report['cases'][case] = {'media': preparation, 'program_sha256': hashlib.sha256(program).hexdigest(),
                                    'all_engine_font_bytes_equal': True, 'screen_differences_from_native': differences,
                                    'engines': engines}
    sheet.save(a.output / 'comparison.png')
    report['diagnosis'] = {
        'firmware_initial_font_pointer': 'D7FB -> DD02 (written by DCB4)',
        'mfd_copy_instruction': '0141: LXI H,DD01',
        'bowling_copy_instruction': '0B43: LXI H,DD01',
        'copy_bytes': 864,
        'copy_transform': 'input | (input >> 1); C5 4E 7E 1F B1 12 13 23 C1 0B 78 B1',
        'byte_before_font': 'DD01=ED; ED | (ED >> 1) = FF',
        'space': 'Wrong origin produces FF 00 00 00 00 00 00 00 00; correct origin gives nine zero bytes.',
        'application_fix_scope': 'Diagnostic initial-copy correction only; both applications also hard-code DD01 in other font-selection/restoration paths.'}
    report['conclusion'] = 'Both applications use DD01; EKTA #0037 initializes its font pointer to DD02. Both emulator builds and MAME reproduce the resulting glyph corruption. The controlled source-address correction clears the space glyph in all three.'
    report['limits'] = ['FEDITOR executable unavailable; no FEDITOR claim.',
        'No physical-hardware run; MAME is a comparison, not a hardware oracle.',
        'Control runs alter the application font source only in the diagnostic harness.',
        'No emulator or historical application changes are justified by these cases.',
        'Initial application screens only; no complete gameplay or MFD function coverage.']
    (a.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
