#!/usr/bin/env python3
"""Reproduce recovered Font Editor graphics and font-address behavior."""
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile
from PIL import Image, ImageDraw
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'verification/juku-scroll'))
from prepare import physical
FILES = ['fed.com', 'feditor.hlp', 'feditor.lat', 'feditor.pc1', 'feditor.pl1',
         'feditor.pl2', 'feditor.pl3', 'feditor.rus']
LATIN_OPERANDS = [0xb1c, 0xb38, 0x1aef, 0x2469, 0x2fa4]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def media(base, archive, destination, control=False):
    raw = bytearray(base.read_bytes())
    assert len(raw) == 819200
    # New disposable filesystem, preserving only the original boot/system tracks.
    for i in range(4096):
        raw[physical(10240 + i)] = 0xe5
    block = 1
    provenance = {}
    with zipfile.ZipFile(archive) as z:
        for slot, name in enumerate(FILES):
            data = bytearray(z.read('font-editor/' + name))
            provenance[name] = {'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            if control and name == 'fed.com':
                # Diagnostic software correction only; production ROM/core are unchanged.
                for operand in LATIN_OPERANDS:
                    off = operand - 0x100
                    assert data[off-1:off+2] == bytes.fromhex('2101dd')
                    data[off] = 2
            records = (len(data) + 127) // 128
            blocks = (len(data) + 4095) // 4096
            assert 0 < records <= 512 and blocks <= 16
            stem, suffix = name.upper().split('.')
            entry = bytearray(32)
            entry[1:12] = stem.encode().ljust(8) + suffix.encode().ljust(3)
            entry[12] = (records - 1) // 128  # EXM=3: one entry covers four logical extents
            entry[15] = (records - 1) % 128 + 1
            entry[16:16+blocks] = bytes(range(block, block+blocks))
            for i, v in enumerate(entry):
                raw[physical(10240 + slot*32 + i)] = v
            for i, v in enumerate(data.ljust(blocks*4096, b'\0')):
                raw[physical(10240 + block*4096 + i)] = v
            decoded = bytes(raw[physical(10240 + block*4096 + i)] for i in range(len(data)))
            assert decoded == data
            block += blocks
    assert block < 197
    destination.write_bytes(raw)
    return provenance


def schedule(path):
    rows = []
    for t, text in [(2000, 'TDD'), (16000, 'fed\r')]:
        for c in text:
            rows += [(t, ord(c), 1), (t+120, 0, 0)]
            t += 280
    for t, key in [(55000, '2'), (58000, 'a'), (60000, 'd'), (62000, 'w'), (64000, 's'),
                   (66000, 'x'), (80000, '\r'), (87000, 0x87), (89000, 'x'),
                   (104000, 0x87), (106000, 's'), (108000, 'x'),
                   (124000, 0x83), (130000, '\x1b'), (136000, '\x1b'),
                   (144000, '\x1b'), (146000, 'Y')]:
        rows += [(t, ord(key) if isinstance(key, str) else key, 1), (t+120, 0, 0)]
    for t, text in [(91000, 'feditor.lat\r'), (110000, 'test.lat\r')]:
        for c in text:
            rows += [(t, ord(c), 1), (t+120, 0, 0)]
            t += 280
    rows.sort()
    path.write_text(''.join(f'{t} {key:02x} {down}\n' for t, key, down in rows))
    return len(rows)


def command(cmd, cwd, log, env=None):
    r = subprocess.run(list(map(str, cmd)), cwd=cwd, env=env, text=True, capture_output=True, timeout=300)
    log.write_text(r.stdout + r.stderr)
    if r.returncode or 'LUA ERROR' in r.stdout + r.stderr:
        raise RuntimeError(str(log))
    return r.stdout


def frames(dest, engine):
    if engine == 'mame':
        rows = list(csv.DictReader(open(dest / 'capture.samples.csv')))
        return [(float(row['seconds']), dest / f'capture-{i:06d}.png') for i, row in enumerate(rows, 1)
                if (dest / f'capture-{i:06d}.png').exists()]
    return [(int(row['cycle']) / 2000000, dest / f"capture-{int(row['sequence']):06d}.pbm")
            for row in csv.DictReader(open(dest / 'capture.frames.csv'))]


def image_at(index, seconds):
    _, path = min(index, key=lambda item: abs(item[0] - seconds))
    return Image.open(path).convert('L'), path


def blank_intervals(dest, engine):
    rows = list(csv.DictReader(open(dest / 'capture.events.csv')))
    intervals, start = [], None
    for r in rows:
        if r['kind'] != 'IW' or int(r['address'], 16) != 0x11:
            continue
        t = float(r['seconds']) if engine == 'mame' else int(r['cycle']) / 2000000
        if int(r['value'], 16) == 0:
            if start is None:
                start = t
        elif start is not None:
            intervals.append((start, t))
            start = None
    return intervals


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ['rom', 'base', 'archive', 'roms', 'mame', 'output']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--baseline', default='577f09ba', help='historical core for the before comparison')
    a = p.parse_args()
    for k, v in vars(a).items():
        if isinstance(v, Path):
            setattr(a, k, v.resolve())
    a.output.mkdir(parents=True, exist_ok=False)
    provenance = media(a.base, a.archive, a.output / 'original.juk')
    media(a.base, a.archive, a.output / 'control.juk', True)
    key_count = schedule(a.output / 'input.keys')
    flags = ['-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-Imachines/juku',
             '-Ithird_party/cpu/i8080', '-Icommon/media', '-Icommon/trace']
    common = ['machines/juku/juk_disk.c', 'machines/juku/juku_fdc.c', 'third_party/cpu/i8080/i8080.c',
              'common/media/media.c', 'common/trace/trace.c']
    old = a.output / 'baseline-source'
    old.mkdir()
    for name in ['juku.c', 'video.inc']:
        (old / name).write_bytes(subprocess.check_output(['git', 'show', a.baseline + ':machines/juku/' + name], cwd=ROOT))
    for engine in ['baseline', 'native', 'paced']:
        source = old / 'juku.c' if engine == 'baseline' else ROOT / 'machines/juku/juku.c'
        command(['cc', *flags, '-DDAC_JUKU_EXPERIMENTAL_FDC_SYNC=' + str(int(engine == 'paced')),
                 'verification/juku-feditor/capture.c', source, *common, '-o', a.output / engine],
                ROOT, a.output / (engine + '-build.log'))
    report = {'issues': [17, 19], 'archive_url': 'https://p6drad-teel.net/~p6der/font-editor.zip',
              'archive_sha256': sha(a.archive), 'rom_sha256': sha(a.rom), 'base_sha256': sha(a.base),
              'files': provenance, 'baseline_revision': a.baseline,
              'mame_version': subprocess.check_output([a.mame, '-help'], text=True).splitlines()[0],
              'cases': {}}
    sheet = Image.new('RGB', (960, 5*265), '#555555')
    draw = ImageDraw.Draw(sheet)
    cases = [('baseline', False), ('native', False), ('paced', False), ('mame', False),
             ('native', True), ('mame', True)]
    for engine, control in cases:
        case = engine + ('-control' if control else '-original')
        dest = a.output / case
        dest.mkdir()
        disk = dest / 'media.juk'
        disk.write_bytes((a.output / ('control.juk' if control else 'original.juk')).read_bytes())
        prefix = dest / 'capture'
        if engine == 'mame':
            env = os.environ.copy()
            env.update(JUKU_FEDITOR_SCHEDULER=str(ROOT / 'verification/juku-scroll/mame.lua'),
                       JUKU_SCROLL_PREFIX=str(prefix), JUKU_SCROLL_KEYS=str(a.output / 'input.keys'),
                       JUKU_SCROLL_FROM='18', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
            stdout = command([a.mame, 'juku', '-bios', '3.43m_37', '-rompath', a.roms, '-flop1', disk,
                '-video', 'none', '-sound', 'none', '-nothrottle', '-seconds_to_run', '152',
                '-skip_gameinfo', '-noreadconfig', '-autoboot_delay', '0', '-autoboot_script',
                ROOT / 'verification/juku-feditor/mame.lua'], dest, dest / 'run.log', env)
        else:
            stdout = command([a.output / engine, a.rom, disk, prefix, a.output / 'input.keys', '152000', '18000'],
                             dest, dest / 'run.log')
        index = frames(dest, engine)
        events = list(csv.DictReader(open(dest / 'capture.events.csv')))
        assert sum(r['kind'] == 'KEY' for r in events) == key_count
        editor, editor_path = image_at(index, 86)
        assert editor.size == (320, 241)
        # First row of space's editing grid. Ignore the cursor in the first cell.
        grid = sum((editor.getpixel((18+8*i, 112)) != 0) << (7-i) for i in range(8))
        assert grid & 0x7f == (0 if control else 0x6d)
        intervals = blank_intervals(dest, engine)
        samples = []
        for start, end in intervals:
            if end-start < .12:
                continue
            im, path = image_at(index, (start+end)/2)
            lit = sum(v != 0 for v in im.getdata())
            samples.append({'start': start, 'end': end, 'lit_pixels_at_midpoint': lit,
                            'frame_sha256': sha(path), 'dimensions': list(im.size)})
        assert samples
        if engine in ['native', 'paced']:
            assert all(s['lit_pixels_at_midpoint'] == 0 for s in samples)
            assert 'prompt=1' in stdout
        if engine == 'mame':
            assert any(s['lit_pixels_at_midpoint'] > 0 for s in samples)
        captures = {}
        for label, t in [('selection', 45), ('editor', 86), ('help', 126), ('exit', 151)]:
            im, path = image_at(index, t)
            captures[label] = {'sha256': sha(path), 'dimensions': list(im.size)}
        saved_image = disk if engine == 'mame' else dest / 'capture.juk'
        saved = saved_image.read_bytes()
        directory = [bytes(saved[physical(10240+i*32+j)] for j in range(32)) for i in range(128)]
        entry = next(e for e in directory if e[0] == 0 and e[1:12] == b'TEST    LAT')
        content = b''.join(bytes(saved[physical(10240+b*4096+i)] for i in range(4096))
                           for b in entry[16:] if b)[:entry[15]*128]
        with zipfile.ZipFile(a.archive) as archive:
            expected = archive.read('font-editor/feditor.lat')
            assert content[1:] == expected[1:] and content[0] in (expected[0], expected[0] | 0x80)
        permitted = {physical(10240+i) for i in range(4096)}
        for block in entry[16:]:
            if block:
                permitted.update(physical(10240+block*4096+i) for i in range(4096))
        before = (a.output / ('control.juk' if control else 'original.juk')).read_bytes()
        assert all(x == y or i in permitted for i, (x, y) in enumerate(zip(before, saved)))
        report['cases'][case] = {'keys': key_count, 'grid_first_row': hex(grid),
            'loaded_and_saved_font_bytes': len(content), 'saved_first_byte': content[0],
            'saved_font_matches_input_except_first_pixel': True, 'unrelated_disk_bytes_unchanged': True,
            'blanking_intervals': samples, 'captures': captures,
            'events_sha256': sha(dest / 'capture.events.csv'),
            'log_sha256': sha(dest / 'run.log')}
        if engine != 'paced':
            row = ['baseline-original', 'native-original', 'mame-original', 'native-control', 'mame-control'].index(case)
            for col, t in enumerate([45, 86, 126]):
                im, _ = image_at(index, t)
                sheet.paste(im, (col*320, row*265+20))
                draw.text((col*320+3, row*265+3), case + ' / ' + str(t) + 's', fill='white')
        print(case, 'verified', flush=True)
    sheet.save(a.output / 'comparison.png')
    report['conclusions'] = {
        'issue17': 'FEDITOR blanks with port 11 alone. MAME ignores this for screen presentation and exposes redraw garbage. The corrected core publishes black raster frames. The previous native core also discarded writes under the high ROM overlay, losing FEDITOR pictures.',
        'issue19': 'The recovered FED.COM hard-codes DD01 in its Latin font selection/restoration paths. With EKTA #0037, space acquires ED pixels. Correcting the five LXI H operands to DD02 in a diagnostic application copy clears the space grid in both engines.',
        'memory_contract_source': 'Mikroarvuti JUKU kasutamisjuhend (1988), section 0.4, printed pp. 10-12; modes 1/2 read high ROM but write video RAM.',
        'limits': ['No physical hardware comparison.', 'ROM #0037 and this recovered application version only.',
                   'Mouse operation and Cyrillic font correction are not covered.',
                   'Load/save preserves the font except the top-left pixel, which may be set by the scripted menu selection; pixel-edit persistence is not established.',
                   'The diagnostic corrected application is not distributed or installed in production.']}
    (a.output / 'results.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
