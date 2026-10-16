#!/usr/bin/env python3
"""Optional independent TOS/M + S600 comparison. Never writes supplied media.

Requires local MAME rt1715w and caller-supplied historical firmware/disk.
Compares stable observations, not instruction timing or physical hardware.
"""
import argparse
import ctypes as C
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from verification.runtime import Runtime

COMMANDS = ['DIR\r', 'TYPE AUTOEXC.SUB\r', 'PIP B:=A:PIP.COM\r', 'DIR B:\r', 'PIP LST:=AUTOEXC.SUB\r']


def sha(data):
    return hashlib.sha256(data).hexdigest()


def screen_text(data):
    return '\n'.join(''.join(chr(c & 127) if 32 <= (c & 127) < 127 else ' '
                             for c in data[i:i + 80]).rstrip()
                     for i in range(0, 1920, 80)).rstrip()


def file_bytes(disk, name):
    """Independent reader for the reference disk's 2 KiB allocation blocks."""
    extents = []
    for i in range(128):
        entry = disk[20480 + i * 32:20480 + (i + 1) * 32]
        if entry[0] or bytes(c & 127 for c in entry[1:12]) != name:
            continue
        blocks = [int.from_bytes(entry[j:j + 2], 'little') for j in range(16, 32, 2)]
        payload = b''.join(disk[20480 + b * 2048:20480 + (b + 1) * 2048]
                           for b in blocks if b)
        extents.append((((entry[14] & 63) << 5) | (entry[12] & 31), payload[:entry[15] * 128]))
    return b''.join(data for _, data in sorted(extents))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media', type=Path, required=True)
    parser.add_argument('--mame', default='mame')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--suite', choices=['basic','wordstar','pascal'], default='basic')
    args = parser.parse_args()
    commands = COMMANDS
    patterns = [r'A>$'] * (len(COMMANDS)+1)
    produced = None
    if args.suite == 'wordstar':
        commands = ['WS DAC.TXT\r', 'HELLO FROM DAC\r', '\x0bD', 'D', 'DAC.TXT\r']
        patterns = [r'A>$', r'DAC\.TXT', 'HELLO FROM DAC', 'EDITING NO FILE', 'NAME OF FILE', 'HELLO FROM DAC']
        produced = (b'DAC     TXT', b'HELLO FROM DAC\r\n')
    elif args.suite == 'pascal':
        commands = ['PIP\r', 'DAC.PAS=CON:\r', "program DAC;\rbegin writeln('HELLO FROM DAC') end.\r", '\x1a', '\r', 'TP\r', 'n', 'wDAC.PAS\r', 'r']
        patterns = [r'A>$', r'\n\*', 'DAC.PAS=CON:', 'begin writeln', r'\n\*', r'A>$', 'TURBO', 'LOGGED DRIVE', 'DAC.PAS', 'HELLO FROM DAC']
        produced = (b'DAC     PAS', b"program DAC;\rbegin writeln('HELLO FROM DAC') end.\r")
    if args.output.resolve() in [(args.media / n).resolve() for n in ['s550.bin','cas.bin','s600.bin','tosm10.img']]:
        parser.error('Output must not overwrite supplied media')
    media = {n: (args.media / n).read_bytes() for n in ['s550.bin', 'cas.bin', 's600.bin', 'tosm10.img']}
    if [len(media[n]) for n in media] != [2048, 256, 2048, 819200]:
        parser.error('Expected 2 KiB boot/keyboard ROMs, 256-byte CAS PROM and 800 KiB raw disk')
    keymap_path = ROOT / 'tests/fixtures/robotron-s600-commands.json'
    keymap = json.loads(keymap_path.read_text())
    subprocess.run(['make', 'build/libdac-runtime.so'], cwd=ROOT, check=True)
    report = {'passed': False, 'core': subprocess.check_output(['git', 'describe', '--always', '--dirty', '--abbrev=40', '--exclude=*'], cwd=ROOT, text=True).strip(),
              'reference': subprocess.check_output([args.mame, '-version'], text=True).strip(),
              'firmware': {n: sha(b) for n, b in media.items()},
              'inputSha256': sha(keymap_path.read_bytes()), 'suite': args.suite, 'commands': commands,
              'checks': [], 'limitations': ['Stable checkpoints, not equal CPU clocks.',
                  'Raster comparison normalizes colours and excludes the final prompt cursor cell.',
                  'MAME agreement is not physical-specimen qualification.',
                  'No injected serial errors or flux-level disk comparison.']}
    try:
        with tempfile.TemporaryDirectory(prefix='dac-historical-reference-') as directory:
            tmp = Path(directory)
            (tmp / 'rt1715w').mkdir()
            for source, dest in [('s550.bin', 's550.bin'), ('cas.bin', '287.bin'), ('s600.bin', 's600.ic8')]:
                (tmp / 'rt1715w' / dest).write_bytes(media[source])
            (tmp / 'a.kdi').write_bytes(media['tosm10.img'])
            (tmp / 'b.kdi').write_bytes(bytes([0xe5]) * 819200)
            # Same switch coordinates in both machines; no host character injection.
            events = []
            frame = 1500
            captures = [frame]
            for command in commands:
                frame += 10
                for char in command:
                    key, mods = keymap[char]
                    events.append((frame, key, mods, 1))
                    events.append((frame + 3, key, mods, 0))
                    frame += 6
                frame += 800
                captures.append(frame)
            lua_events = ','.join('{%d,%d,%d,%d}' % e for e in events)
            lua_captures = ','.join(map(str, captures))
            script = r'''
local m=manager.machine
local program=m.devices[':maincpu'].spaces['program']
local ports=m.devices[':maincpu'].spaces['io']
local bank=0
local tap=ports:install_write_tap(0x24,0x24,'dac-bank',function(a,v) bank=v end)
local events={EVENTS};local captures={CAPTURES}
local frame=0;local event=1;local capture=1
local rows={'row_00','row_10','row_20','row_30','row_40','row_50','row_60','row_70','row_08','row_18','row_28','row_38','row_48'}
local function contact(key,down)
 local port=m.ioport.ports[':'..rows[(key//8)+1]]
 for _,field in pairs(port.fields) do
  if field.mask==(1<<(key%8)) then field:set_value(down);return end
 end
 error('Missing matrix contact '..key)
end
emu.register_frame_done(function()
 frame=frame+1
 while events[event] and events[event][1]==frame do
  local e=events[event];contact(e[2],e[4])
  if (e[3]&1)~=0 then contact(65,e[4]) end
  if (e[3]&2)~=0 then contact(64,e[4]) end
  event=event+1
 end
 if captures[capture]~=frame then return end
 local previous=bank;ports:write_u8(0x24,0)
 local f=assert(io.open('screen-'..capture..'.bin','wb'))
 for address=0x3000,0x377f do f:write(string.char(program:read_u8(address))) end
 f:close();ports:write_u8(0x24,previous)
 local pixels,width,height=m.screens[':screen']:pixels()
 f=assert(io.open('pixels-'..capture..'.bin','wb'));f:write(pixels);f:close()
 f=assert(io.open('size-'..capture..'.txt','w'));f:write(width..' '..height);f:close()
 capture=capture+1
 if capture>#captures then m:exit() end
end)
'''.replace('EVENTS', lua_events).replace('CAPTURES', lua_captures)
            (tmp / 'probe.lua').write_text(script)
            result = subprocess.run([args.mame, 'rt1715w', '-rompath', str(tmp), '-flop1', str(tmp / 'a.kdi'),
                '-flop2', str(tmp / 'b.kdi'), '-printout', str(tmp / 'printer.prn'), '-video', 'none', '-sound', 'none', '-nothrottle',
                '-skip_gameinfo', '-autoboot_script', str(tmp / 'probe.lua'), '-seconds_to_run', str((frame // 50) + 30)],
                cwd=tmp, env={**os.environ, 'SDL_VIDEODRIVER': 'dummy'}, capture_output=True, text=True, timeout=240)
            if result.returncode or not (tmp / f'screen-{len(commands)+1}.bin').exists():
                raise RuntimeError('MAME did not finish all checkpoints: ' + result.stdout[-3000:] + result.stderr[-3000:])

            with Runtime(ROOT / 'build/libdac-runtime.so', 'robotron1715m') as runtime:
                lib, session = runtime.lib, runtime.session
                for name, restype, argtypes in [
                    ('dac_tap', C.c_int, [C.c_void_p, C.c_uint, C.c_uint]),
                    ('dac_video', C.c_void_p, [C.c_void_p]),
                    ('dac_printer_data', C.c_void_p, [C.c_void_p]),
                    ('dac_printer_size', C.c_uint, [C.c_void_p]),
                    ('dac_width', C.c_uint, [C.c_void_p]), ('dac_height', C.c_uint, [C.c_void_p]),
                    ('dac_disk_data_unit', C.c_void_p, [C.c_void_p, C.c_uint])]:
                    fn = getattr(lib, name); fn.restype = restype; fn.argtypes = argtypes
                for slot, name in [(0, 's550.bin'), (1, 'cas.bin'), (3, 's600.bin')]:
                    runtime.load(slot, media[name])
                runtime.mount(0, media['tosm10.img'], args.suite != 'basic')
                runtime.mount(1, bytes([0xe5]) * 819200, True)
                runtime.power()

                def run(clocks):
                    while clocks:
                        clocks -= runtime.run(min(clocks, 100000))

                run(100_000_000)
                for index in range(len(commands)+1):
                    if index:
                        for char in commands[index - 1]:
                            runtime.checked('dac_tap', *keymap[char])
                            run(480000)
                        run(64_000_000)
                    actual = screen_text(runtime.peek('video', 0, 1920))
                    expected = screen_text((tmp / f'screen-{index + 1}.bin').read_bytes())
                    # Let a complete raster finish after the last guest write.
                    run(160000)
                    video = lib.dac_video(session)
                    width, height = lib.dac_width(session), lib.dac_height(session)
                    reference_size = list(map(int, (tmp / f'size-{index + 1}.txt').read_text().split()))
                    pixels = C.string_at(video, width * height * 4)
                    reference = (tmp / f'pixels-{index + 1}.bin').read_bytes()
                    raster_match = [width, height] == reference_size
                    differences = []
                    lines = expected.split('\n')
                    cursor = ((len(lines) - 1) * 12, len(lines[-1]) * 8)
                    if raster_match:
                        for y in range(height):
                            for x in range(width):
                                if cursor[0] <= y < cursor[0] + 12 and cursor[1] <= x < cursor[1] + 8:
                                    continue
                                offset = (y * width + x) * 4
                                if (pixels[offset + 1] > 100) != (reference[offset + 1] > 100):
                                    if len(differences) < 16:
                                        differences.append([x, y])
                                    raster_match = False
                    check = {'checkpoint': 'boot' if not index else commands[index - 1].strip(),
                             'textEqual': actual == expected, 'milestone': bool(re.search(patterns[index],actual,re.I)), 'prompt': actual.endswith('\nA>'),
                             'rasterEqualOutsideCursor': raster_match, 'firstPixelDifferences': differences,
                             'dacSize': [width, height], 'mameSize': reference_size,
                             'dacText': actual, 'mameText': expected}
                    report['checks'].append(check)
                expected_file = file_bytes(media['tosm10.img'], b'PIP     COM')
                native_b = C.string_at(lib.dac_disk_data_unit(session, 1), 819200)
                reference_b = (tmp / 'b.kdi').read_bytes()
                report['copy'] = {'bytes': len(expected_file), 'sha256': sha(expected_file),
                    'dacEqual': file_bytes(native_b, b'PIP     COM') == expected_file,
                    'mameEqual': file_bytes(reference_b, b'PIP     COM') == expected_file}
                if produced:
                    native_a = C.string_at(lib.dac_disk_data_unit(session, 0), 819200)
                    reference_a = (tmp / 'a.kdi').read_bytes()
                    filename, expected_content = produced
                    native_content = file_bytes(native_a, filename).split(b'\x1a')[0]
                    reference_content = file_bytes(reference_a, filename).split(b'\x1a')[0]
                    report['savedFile'] = {'name': filename.decode(), 'expected': expected_content.decode(),
                        'dacEqual': native_content == expected_content, 'mameEqual': reference_content == expected_content,
                        'dacSha256': sha(native_content), 'mameSha256': sha(reference_content)}
                    # Application cursor position/attributes differ from the final CCP prompt.
                    # Preserve raster observations, but qualify text and saved bytes here.
                    report['passed'] = all(c['textEqual'] and c['milestone'] for c in report['checks']) and report['savedFile']['dacEqual'] and report['savedFile']['mameEqual']
                    report['limitations'].append('Application raster differences are recorded but not qualified; prompt cursor exclusion only applies to basic suite.')
                else:
                    printer_expected = file_bytes(media['tosm10.img'], b'AUTOEXC SUB').split(b'\x1a')[0]
                    printer_actual = C.string_at(lib.dac_printer_data(session), lib.dac_printer_size(session))
                    printer_reference = (tmp / 'printer.prn').read_bytes()
                    report['printer'] = {'bytes': len(printer_expected), 'dacEqual': printer_actual == printer_expected, 'mameEqual': printer_reference == printer_expected, 'dacSha256': sha(printer_actual), 'mameSha256': sha(printer_reference)}
                    report['passed'] = all(c['textEqual'] and c['milestone'] and c['rasterEqualOutsideCursor'] for c in report['checks']) and len(expected_file) > 0 and report['copy']['dacEqual'] and report['copy']['mameEqual'] and report['printer']['dacEqual'] and report['printer']['mameEqual']
    except Exception as error:
        report['error'] = str(error)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'output': str(args.output), 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
