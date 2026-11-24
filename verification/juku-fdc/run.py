#!/usr/bin/env python3
"""Issue 25 read-path investigation; outputs remain outside the repository.

Requires a C compiler, MAME, Pillow, EKTA #0037 and a Juku EKDOS disk.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(HERE.parent / 'juku-scroll'))
from analyze import font_table, pixels, text_rows

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p = argparse.ArgumentParser()
    for name in ['rom', 'disk', 'roms', 'mame', 'output']:
        p.add_argument('--' + name, required=True, type=Path)
    a = p.parse_args()
    for name in vars(a):
        setattr(a, name, getattr(a, name).resolve())
    a.output.mkdir(parents=True, exist_ok=False)
    subprocess.run(['make', 'build/libdac-juku.a'], cwd=ROOT, check=True)
    exe = a.output / 'probe'
    subprocess.run([os.getenv('CC', 'cc'), '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror',
                    '-Imachines/juku', '-Ithird_party/cpu/i8080', '-Icommon/media', '-Icommon/trace',
                    str(HERE / 'probe.c'), 'build/libdac-juku.a', '-o', str(exe)], cwd=ROOT, check=True)
    font = font_table(a.rom.read_bytes())
    report = {'provenance': {'rom_sha256': digest(a.rom), 'disk_sha256': digest(a.disk),
              'core_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
              'mame_version': subprocess.check_output([str(a.mame), '-help'], text=True).splitlines()[0]},
              'cases': {}}
    for name, paced in [('stock', 0), ('paced_without_wait', 1)]:
        prefix = a.output / name
        output = subprocess.check_output([str(exe), str(a.rom), str(a.disk), str(prefix), str(paced)], text=True, timeout=60)
        result = json.loads(output)
        rows = list(csv.DictReader(prefix.with_suffix('.csv').open()))
        reads = [r for r in rows if r['op'] == 'db' and r['reg'] == '1f']
        result['common_read_gaps_cpu_cycles'] = Counter(int(b['cycle']) - int(c['cycle']) for c, b in zip(reads, reads[1:])).most_common(3)
        result['final_text'] = text_rows(prefix.with_suffix('.ram').read_bytes()[0xd800:], font)
        result['trace_sha256'] = digest(prefix.with_suffix('.csv'))
        report['cases'][name] = result
    dest = a.output / 'mame'; dest.mkdir()
    media = dest / 'media.juk'; shutil.copyfile(a.disk, media); media.chmod(0o444)
    keys = []
    for start, word in [(2000, 'TDD'), (16000, 'dir\r')]:
        for i, c in enumerate(word):
            keys.extend([(start+i*280, ord(c), 1), (start+i*280+120, 0, 0)])
    schedule = dest / 'input.keys'
    schedule.write_text(''.join(f'{t} {k:02x} {d}\n' for t, k, d in keys))
    env = os.environ.copy()
    env.update(JUKU_SCROLL_SCRIPT=str(HERE.parent / 'juku-scroll/mame.lua'),
               JUKU_SCROLL_PREFIX=str(dest / 'capture'), JUKU_SCROLL_KEYS=str(schedule),
               JUKU_SCROLL_FROM='29.8', SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy')
    cmd = [str(a.mame), 'juku', '-bios', '3.43m_37', '-rompath', str(a.roms), '-flop1', str(media),
           '-video', 'none', '-sound', 'none', '-nothrottle', '-seconds_to_run', '30',
           '-skip_gameinfo', '-noreadconfig', '-autoboot_delay', '0', '-autoboot_script', str(HERE / 'mame.lua')]
    run = subprocess.run(cmd, cwd=dest, env=env, capture_output=True, text=True, timeout=120)
    (dest / 'run.log').write_text(run.stdout + run.stderr)
    if run.returncode or 'LUA ERROR' in run.stdout + run.stderr:
        raise RuntimeError(run.stdout + run.stderr)
    assert sum(r.startswith('KEY,') for r in (dest / 'capture.events.csv').read_text().splitlines()) == len(keys)
    assert (dest / 'capture.ram').exists()
    trace = dest / 'capture.fdc.csv'
    rows = list(csv.DictReader(trace.open()))
    reads = [r for r in rows if r['op'] == 'read' and r['reg'] == '1f']
    report['cases']['mame'] = {
        'data_read_callbacks_including_retries': len(reads),
        'callback_pcs': dict(Counter(r['pc'] for r in reads)),
        'common_read_callback_gaps_us': Counter(round((float(b['seconds'])-float(c['seconds']))*1e6, 2) for c, b in zip(reads, reads[1:])).most_common(3),
        'commands': dict(Counter(r['value'] for r in rows if r['op'] == 'write' and r['reg'] == '1c')),
        'final_text': text_rows(pixels(sorted(dest.glob('capture-*.png'))[-1]), font),
        'trace_sha256': digest(trace)}
    # These are recorded observations, not golden counts or a demand that a
    # corrected emulator preserve the diagnostic failure.
    (a.output / 'measurements.json').write_text(json.dumps(report, indent=2) + '\n')
    print(a.output / 'measurements.json')

if __name__ == '__main__':
    main()
