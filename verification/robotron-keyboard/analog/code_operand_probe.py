#!/usr/bin/env python3
"""Review complete typed code scans and lossless fixed-reference differences."""
import argparse, copy, json, lzma, math, os, platform, shutil, subprocess, tempfile
from pathlib import Path
import code_binding_probe as base
from thread_board_reachability import analyze
from ttl7406_probe import sha
HERE = Path(__file__).resolve().parent


def block(lines, start):
    a = lines[start].split()
    if len(a) != 5 or a[0] != 'VCO_BEGIN' or a[1] not in ('R','F','D'):
        raise ValueError('Invalid operand frame')
    mode, tick, total, count = a[1], int(a[2]), int(a[3]), int(a[4])
    if tick < 0 or not 0 <= count <= total or not total:
        raise ValueError('Invalid operand counts')
    if start + 1 + count >= len(lines):
        raise ValueError("Truncated operand frame")
    rows = {}
    for i in range(start+1, start+1+count):
        a = lines[i].split()
        if len(a) < 3 or a[0] != 'VCO_ROW' or int(a[1]) <= (next(reversed(rows)) if rows else 0):
            raise ValueError('Unordered or malformed operand row')
        fields = {}
        for entry in a[3:]:
            key, value = entry.split('=')
            if key in fields:
                raise ValueError('Duplicate operand field')
            fields[key] = value
        rows[int(a[1])] = dict(opcode=a[2], fields=fields)
    end = start+1+count
    if lines[end] != f'VCO_END {count}' or (mode != 'D' and count != total):
        raise ValueError('Incomplete operand frame')
    return dict(mode=mode, tick=tick, total=total, rows=rows), end+1


def reconstruct(reference, delta):
    if delta['mode'] != 'D' or delta['total'] != len(reference) or not set(delta['rows']) <= set(reference):
        raise ValueError('Delta reference mismatch')
    if any(reference[i] == row for i,row in delta['rows'].items()):
        raise ValueError('Redundant delta record')
    return reference | delta['rows']


def changed(before, after, field):
    if before['binding'] != after['binding'] or before['tick'] != after['tick']:
        raise ValueError('Operand fault changed thread/PC state')
    expected = copy.deepcopy(before['rows'])
    key = ('number','cptr','handle')[field]
    identity = next((i for i,r in expected.items() if key in r['fields']), None)
    if identity is None:
        raise ValueError('Missing operand fault target')
    value = expected[identity]['fields'][key]
    expected[identity]['fields'][key] = str(int(value)^1) if field == 0 else '1/0' if field == 1 else '1'
    if after['rows'] != expected:
        raise ValueError('Wrong operand mutation or unrelated code change')


def stdout(root, mode):
    path = root/(mode+'.stdout')
    if path.exists():return path.read_text()
    with lzma.open(str(path)+'.xz','rt') as source:return source.read()


def review(root):
    compiled = analyze((root/'probe.vvp').read_text())
    count = sum(compiled['opcodeCounts'].values()) + 1
    chunks = math.ceil(count/1023)
    ids = set()
    for chunk in range(chunks):
        used = min(1023, count-chunk*1023)
        ids.update(chunk*1024+i+1 for i in range(used))
        ids.add((chunk+1)*1024)
    schemas = json.loads((HERE/'reports/code-operand-contract/assessment.json').read_text())
    fields = {v['handler']: {f['field'] for f in v['fields']} for v in schemas['instructions'].values()}
    fields.update(of_ZOMBIE=set(), of_CHUNK_LINK={'cptr'}, of_DELAY={'bit_idx[0]','bit_idx[1]'})
    pairs = dense_bytes = sparse_bytes = 0
    faults = {i:0 for i in range(4)}
    canonical_reference = None
    with tempfile.TemporaryDirectory() as folder:
        stripped = Path(folder)
        for mode in ('baseline','disabled','enabled','corrupt'):
            lines = stdout(root, mode).splitlines()
            clean=[];i=0;reference=None;before=None;pending=None;restored=False
            while i < len(lines):
                line=lines[i]
                if line.startswith('VCO_BEGIN R '):
                    if reference is not None or mode not in ('enabled','corrupt'):
                        raise ValueError('Unexpected reference reset')
                    frame,i=block(lines,i);reference=frame['rows']
                    if set(reference)!=ids:
                        raise ValueError('Missing allocated or implicit instructions')
                    pointers={}
                    normalized=copy.deepcopy(reference)
                    for identity,row in reference.items():
                        if row['opcode'] not in fields or set(row['fields'])!=fields[row['opcode']]:
                            raise ValueError('Wrong typed operand schema')
                        for key,value in row['fields'].items():
                            if key in ('number','bit_idx[0]','bit_idx[1]'):
                                if int(value)<0:raise ValueError('Invalid immediate')
                                continue
                            if key in ('cptr','cptr2'):
                                pointer,target=map(int,value.split('/'))
                                if target not in ids and not (row['opcode']=='of_CHUNK_LINK' and pointer==target==0):
                                    raise ValueError('Invalid code target')
                                if bool(pointer)!=bool(target):raise ValueError('Invalid code target identity')
                            else:
                                pointer=int(value);target=None
                                if not pointer:raise ValueError('Missing object reference')
                            if pointer and pointer not in pointers:pointers[pointer]=len(pointers)+1
                            normalized[identity]['fields'][key]=(pointers.get(pointer,0),target)
                    if canonical_reference is None:canonical_reference=normalized
                    elif normalized!=canonical_reference:raise ValueError('Changed initial code image')
                    continue
                if line in ('VTM_BEFORE','VTM_REPEAT','VTM_RESTORED','VOM_RESTORED') or line.startswith(('VTM_CHANGED ','VOM_CHANGED ')):
                    if reference is None:raise ValueError('Missing reference image')
                    split=next((j for j in range(i+1,len(lines)) if lines[j].startswith('VCO_BEGIN F ')),None)
                    if split is None:raise ValueError('Missing full operand frame')
                    binding=base.parse_snapshot(lines[i+1:split])
                    full,next_index=block(lines,split)
                    delta,end=block(lines,next_index)
                    if full['mode']!='F' or full['tick']!=delta['tick'] or full['tick']!=binding['threads']['tick'] or reconstruct(reference,delta)!=full['rows']:
                        raise ValueError('Lossy operand delta or time mismatch')
                    pairs+=1;dense_bytes+=sum(len(l)+1 for l in lines[split:next_index]);sparse_bytes+=sum(len(l)+1 for l in lines[next_index:end])
                    shot=dict(binding=binding,rows=full['rows'],tick=full['tick'])
                    if line=='VTM_BEFORE':
                        if pending is not None or shot['rows']!=reference:raise ValueError('Changed normal code or unfinished fault')
                        before=shot
                    elif before is None:raise ValueError('Orphan operand snapshot')
                    elif line.startswith('VOM_CHANGED '):
                        if mode!='corrupt' or pending is not None:raise ValueError('Unexpected operand fault')
                        pending=int(line.split()[1]);restored=False
                        if pending not in (0,1,2):raise ValueError('Unknown operand fault')
                        changed(before,shot,pending)
                    elif line=='VOM_RESTORED':
                        if pending is None or restored or shot!=before:raise ValueError('Operand fault not restored')
                        restored=True
                    elif line in ('VTM_REPEAT','VTM_RESTORED'):
                        if shot!=before:raise ValueError('Observer/PC fault changed operands')
                    elif shot['rows']!=before['rows']:raise ValueError('PC fault changed allocated code')
                    if line.startswith('VTM_'):
                        clean.append(line);clean.extend(lines[i+1:split])
                    i=end;continue
                if line=='VOM_REFUSAL 3':
                    if pending is not None or mode!='corrupt':raise ValueError('Unexpected refusal')
                    pending=3;restored=False
                elif line.startswith('VOM_FAULT '):
                    if pending is None or not restored or line!=f'VOM_FAULT {pending} 1 1':raise ValueError('Incomplete operand control')
                    faults[pending]+=1;pending=None
                else:
                    if pending is not None or line.startswith(('VOM_','VCO_')):raise ValueError('Unexpected operand record')
                    clean.append(line)
                i+=1
            if pending is not None or bool(reference)!=(mode in ('enabled','corrupt')):raise ValueError('Missing operand coverage')
            (stripped/(mode+'.stdout')).write_text('\n'.join(clean)+'\n')
            shutil.copyfile(root/(mode+'.stderr'),stripped/(mode+'.stderr'))
        result=base.review(stripped)
    if any(v!=4 for v in faults.values()) or sparse_bytes>=dense_bytes:
        raise ValueError('Missing faults or lossless reduction')
    result.update(completeAllocatedOperandCoverage=True, denseAndDeltaExactlyEqual=True,
                  matchedOperandSnapshots=pairs, operandFaults=faults, allocatedInstructions=len(ids),
                  denseOperandBytes=dense_bytes, deltaOperandBytes=sparse_bytes,
                  scope='Complete allocated typed operand image, fixed-reference reconstruction and restored immediate/code/handle faults; unknown native family refused. All original PC binding controls preserved.',
                  notEstablished=['Referenced object contents', 'Board integration and runtime/evidence budgets', 'General code immutability, freed storage or rollback'])
    return result


def run(candidate,baseline,modules,out):
    candidate=candidate.resolve();baseline=baseline.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    build=json.loads((candidate/'build.json').read_text())
    for n,h in build['outputs'].items():
        if sha(candidate/n)!=h:raise ValueError('Changed built runtime')
    for ext in ('c','v'):shutil.copy2(HERE/('fixtures/code_operand_probe.c' if ext=='c' else 'fixtures/code_binding_probe.v'),out/f'probe.{ext}')
    commands=[['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')]]
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
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Runtime changed during controls')
    shutil.copy2(candidate/'build.json',out/'build.json')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')
    (out/'run.json').write_text(json.dumps({'qualified':False,'commands':commands,'runs':runs,'dependencies':pins,'candidateBuildSha256':sha(candidate/'build.json'),'sources':{n:sha(HERE/n) for n in ('code_operand_probe.py','code_binding_probe.py','thread_board_reachability.py','reports/code-operand-contract/assessment.json','thread_probe.py','thread_compact_probe.py','fixtures/code_operand_probe.c','fixtures/code_binding_probe.v')}},indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('candidate','baseline','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        if json.loads(json.dumps(review(a.check)))!=json.loads((a.check/'assessment.json').read_text()):raise ValueError('Changed assessment')
        print('Complete operand reconstruction and restored faults verified.')
    else:
        if not all((a.candidate,a.baseline,a.modules,a.out)):p.error('Need runtime paths and fresh output')
        run(a.candidate,a.baseline,a.modules,a.out)
