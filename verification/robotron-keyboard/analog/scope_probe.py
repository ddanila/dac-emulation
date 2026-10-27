#!/usr/bin/env python3
"""Validate actual scope membership independently of live thread lifetime."""
import argparse
import copy
import json
import tempfile
import os, platform, shutil, subprocess
from pathlib import Path
import thread_lifecycle_probe as lifecycle
from ttl7406_probe import sha
from thread_board_reachability import analyze

HERE = Path(__file__).resolve().parent


def parse_snapshot(lines):
    split = next((i for i, line in enumerate(lines) if line.startswith('VSC_BEGIN ')), None)
    if split is None:
        raise ValueError('Missing scope inventory')
    result = lifecycle.parse_snapshot(lines[:split])
    head = lines[split].split()
    if head != ['VSC_BEGIN', '1', str(result['threads']['tick'])]:
        raise ValueError('Scope timestamp/version mismatch')
    scopes = []
    i = split + 1
    while i < len(lines) and lines[i].startswith('VSC_SCOPE '):
        a = lines[i].split()
        if len(a) != 6:
            raise ValueError('Invalid scope header')
        identity, pointer, parent, kind, count = int(a[1]), int(a[2], 16), int(a[3]), int(a[4]), int(a[5])
        if identity != len(scopes) + 1 or not pointer or not 0 <= parent < identity or count < 0:
            raise ValueError('Invalid scope identity/hierarchy')
        i += 1
        members = []
        for _ in range(count):
            if i >= len(lines):
                raise ValueError('Missing scope member')
            a = lines[i].split()
            if len(a) != 2 or a[0] != 'VSC_MEMBER' or int(a[1]) <= (members[-1] if members else 0):
                raise ValueError('Invalid scope member order')
            members.append(int(a[1]))
            i += 1
        scopes.append(dict(id=identity, pointer=pointer, parent=parent, kind=kind, members=members))
    if not scopes or lines[i:] != [f'VSC_END {len(scopes)}'] or len({s['pointer'] for s in scopes}) != len(scopes):
        raise ValueError('Incomplete/aliased scope inventory')
    result['scopes'] = scopes
    return result


def validate(snapshot):
    lifecycle.validate(snapshot)
    live = {t['id']: t for t in snapshot['threads']['threads']}
    pointers = {s['pointer'] for s in snapshot['scopes']}
    members = set()
    for scope in snapshot['scopes']:
        for identity in scope['members']:
            if identity in members or identity not in live or live[identity]['scope'] != scope['pointer']:
                raise ValueError('Unknown, duplicated or wrongly owned scope member')
            members.add(identity)
    for identity, thread in live.items():
        if thread['scope'] not in pointers:
            raise ValueError('Unknown thread scope')
        if identity not in members and thread['state'][4] != '1':
            raise ValueError('Non-ended live thread lost scope membership')
    return members


def changed_snapshot(before, changed):
    expected = copy.deepcopy(before)
    target = next((s for s in expected['scopes'] if s['members']), None)
    if target is None:
        raise ValueError('No membership fault target')
    target['members'].pop(0)
    if changed != expected:
        raise ValueError('Wrong scope fault or unrelated mutation')


def review(root):
    compiled = analyze((root / "probe.vvp").read_text())
    if any(s["automatic"] for s in compiled["scopes"]):
        raise ValueError("Normal fixture must have static scopes")
    expected_scopes = len(compiled["scopes"])
    coverage = set()
    faults = 0
    trajectory = None
    with tempfile.TemporaryDirectory() as directory:
        stripped = Path(directory)
        for mode in ('baseline', 'disabled', 'enabled', 'corrupt'):
            lines = (root / (mode + '.stdout')).read_text().splitlines()
            clean = []
            i = 0
            before = None
            scope_fault = False
            scope_restored = False
            shots = []
            layout = None
            while i < len(lines):
                line = lines[i]
                if line in ('VTM_BEFORE', 'VTM_REPEAT', 'VTM_RESTORED') or line.startswith('VTM_CHANGED '):
                    end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith('VSC_END ')), None)
                    if end is None:
                        raise ValueError('Truncated scope snapshot')
                    raw = lines[i + 1:end + 1]
                    snapshot = parse_snapshot(raw)
                    if line == 'VTM_BEFORE':
                        if scope_fault:
                            raise ValueError('Unfinished scope fault')
                        before = snapshot
                        members = validate(before)
                        current_layout = [{k: v for k, v in s.items() if k != 'members'} for s in before['scopes']]
                        if len(current_layout) != expected_scopes or (layout is not None and current_layout != layout):
                            raise ValueError('Missing or rebound compiled scope')
                        layout = current_layout
                        if any(not s['members'] for s in before['scopes']):
                            coverage.add('empty-scope')
                        for t in before['threads']['threads']:
                            if t['id'] not in members:
                                if t['state'][8] == '1':
                                    coverage.add('reaped-deferred-delete')
                                if t['state'][5] == '1' and t['state'][7] == '1':
                                    coverage.add('disabled-pending-zombie')
                        shots.append([{k: v for k, v in s.items() if k != 'pointer'} for s in before['scopes']])
                    elif before is None:
                        raise ValueError('Orphan scope snapshot')
                    elif line == 'VTM_CHANGED 12':
                        if scope_fault or mode != 'corrupt':
                            raise ValueError('Unexpected scope fault')
                        changed_snapshot(before, snapshot)
                        scope_fault = True
                        scope_restored = False
                    elif line in ('VTM_REPEAT', 'VTM_RESTORED'):
                        if snapshot != before:
                            raise ValueError('Scope observation/restoration changed state')
                        if scope_fault:
                            if line != 'VTM_RESTORED' or scope_restored:
                                raise ValueError('Unexpected fault restoration')
                            scope_restored = True
                    elif snapshot['scopes'] != before['scopes']:
                        raise ValueError('Lifecycle fault mutated scope membership')
                    if not scope_fault:
                        clean.append(line)
                        clean.extend(l for l in raw if not l.startswith('VSC_'))
                    i = end + 1
                    continue
                if line.startswith('VTM_FAULT 12 '):
                    if not scope_fault or not scope_restored or line != 'VTM_FAULT 12 1 1' or lines[i - 1].split()[0] != 'VSC_END':
                        raise ValueError('Invalid membership fault result')
                    scope_fault = False
                    faults += 1
                else:
                    if line.startswith('VSC_') or scope_fault:
                        raise ValueError('Unexpected scope record')
                    clean.append(line)
                i += 1
            if scope_fault:
                raise ValueError('Unfinished scope fault')
            if shots:
                if trajectory is None:
                    trajectory = shots
                elif shots != trajectory:
                    raise ValueError('Changed normal scope trajectory')
            (stripped / (mode + '.stdout')).write_text('\n'.join(clean) + '\n')
            (stripped / (mode + '.stderr')).write_bytes((root / (mode + '.stderr')).read_bytes())
        result = lifecycle.review(stripped)
    if faults != 7 or coverage != {'empty-scope', 'reaped-deferred-delete', 'disabled-pending-zombie'}:
        raise ValueError('Missing scope lifecycle/fault coverage: ' + str(coverage))
    result.update(scopeMembershipControlsPassed=True, restoredScopeFaults=faults,
                  scopeCoverage=sorted(coverage),
                  scope='Static scope hierarchy and actual membership across thread lifecycle; restored membership faults preserve all preceding thread/queue controls and complete output.',
                  notEstablished=['Automatic scopes/context contents', 'Board integration', 'Scope intern contents, code operands, net/array/fanout state', 'Freed storage or general rollback'])
    result['automaticScopeRefusalPassed'] = review_refusal(root)
    return result


def review_refusal(root):
    runs = json.loads((root / 'run.json').read_text())['runs']
    reference = None
    for mode in ('baseline', 'disabled', 'enabled', 'corrupt'):
        name = 'unsupported-' + mode
        lines = (root / (name + '.stdout')).read_text().splitlines()
        if (root / (name + '.stderr')).read_text():
            raise ValueError('Unexpected refusal diagnostics')
        if mode in ('enabled', 'corrupt'):
            if runs[name]['exitCode'] != 2 or lines != ['VTM_API 0 1']:
                raise ValueError('Unsupported scope accepted or continued')
        else:
            if runs[name]['exitCode'] != 0 or lines[:3] != ['VTM_API 0 ' + str(int(mode != 'baseline')), 'VTM_DONE 0', 'CONTINUED 1000'] or len(lines) != 4 or '$finish called at 1000 (1ps)' not in lines[-1]:
                raise ValueError('Unsupported fixture control failed')
            if reference is None:
                reference = lines[1:]
            elif reference != lines[1:]:
                raise ValueError('Disabled scope observer changed continuation')
    return True


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/scope_probe.c' if ext=='c' else 'fixtures/scope_probe.v'),out/f'probe.{ext}')
    shutil.copy2(HERE/'fixtures/scope_unsupported.v',out/'unsupported.v')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
    commands.append(['iverilog','-g2012','-o',str(out/'unsupported.vvp'),str(out/'unsupported.v')])
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    commands.append(['cc',*flags,'-I'+str(candidate),'-o',str(out/'probe.vpi'),str(out/'probe.c')])
    for cmd in commands:subprocess.run(cmd,check=True)
    paths=[baseline,candidate/'vvp/libvvp.so',candidate/'vvp/vvp',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};runs={}
    for name,lib,mode in [('baseline',baseline,'off'),('disabled',candidate/'vvp/libvvp.so','off'),('enabled',candidate/'vvp/libvvp.so','on'),('corrupt',candidate/'vvp/libvvp.so','corrupt')]:
        env=dict(os.environ,K7658_THREAD_PROBE=mode);env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(lib.parent)
        cmd=[str(candidate/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe','probe.vvp']
        r=subprocess.run(cmd,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
        runs[name]={'command':cmd,'exitCode':r.returncode,'library':str(lib),'mode':mode};r.check_returncode()
        cmd = cmd[:-1] + ['unsupported.vvp']
        r = subprocess.run(cmd, cwd=out, env=env, capture_output=True, text=True, timeout=30)
        name = 'unsupported-' + name
        (out/(name+'.stdout')).write_text(r.stdout)
        (out/(name+'.stderr')).write_text(r.stderr)
        runs[name] = dict(command=cmd, exitCode=r.returncode, library=str(lib), mode=mode)

    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('scope_probe.py','thread_board_reachability.py','thread_lifecycle_probe.py','thread_probe.py','thread_compact_probe.py','thread_board_review.py','fixtures/scope_probe.c','fixtures/scope_probe.v','fixtures/scope_unsupported.v')}},indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Scope membership, lifecycle controls and unsupported-profile refusal verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
