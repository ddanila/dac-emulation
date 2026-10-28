#!/usr/bin/env python3
"""Replay memory destruction/reuse through the built three-stream metadata logger."""
import argparse,json,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from retained_evidence import check
from memory_lifecycle import review as native_review
from scope_metadata_compact import Decoder
from memory_compact import MemoryDecoder


def images(text):
    lines=text.splitlines();result=[];i=0
    while i<len(lines):
        tag=lines[i].split()[0] if lines[i] else ''
        if tag in ('VMM_BEGIN','VSM_BEGIN','VSMR_BEGIN'):
            start=i;end=tag.replace('_BEGIN','_END')+' '
            while i<len(lines) and not lines[i].startswith(end):i+=1
            if i==len(lines):raise ValueError('Missing native lifecycle footer')
            result.append('\n'.join(lines[start:i+1])+'\n')
        i+=1
    return result


def review(root):
    native=root/'native';check(native);lifecycle=native_review(native)
    receipt=json.loads((root/'run.json').read_text());build=json.loads((root/'bridge-build.json').read_text())
    if receipt['exitCode'] or (root/'stderr.txt').read_text():raise ValueError('Native logger failed')
    if sha(root/'bridge-build.json')!=receipt['bridgeBuildSha256'] or sha(root/'icarus_shim.c')!=receipt['generatedShimSha256'] or receipt['generatedShimSha256']!=build['outputs']['icarus_shim.c']:raise ValueError('Changed built logger identity')
    if sha(native/'run.json')!=receipt['nativeReceiptSha256'] or sha(native/'enabled.stdout')!=receipt['nativeOutputSha256']:raise ValueError('Changed native lifecycle identity')
    shim=(root/'icarus_shim.c').read_text();a=shim.index('/* Compact only serialized log records.');b=shim.index('static int robotron_scope_metadata_inventory(FILE*out',a)
    if (root/'logger.h').read_text()!=shim[a:b]:raise ValueError('Logger differs from built bridge')
    expected=images((native/'enabled.stdout').read_text())
    if len(expected)!=30 or ''.join(expected)!=(root/'dense.txt').read_text():raise ValueError('Missing native lifecycle streams')
    decoders={'VMMD':MemoryDecoder(),'VSMD':Decoder(),'VSMRD':Decoder(True)}
    lines=(root/'compact.txt').read_text().splitlines();decoded=[];i=0;frames=[]
    while i<len(lines):
        tag=lines[i].split()[0].replace('_BEGIN','');start=i
        if tag not in decoders:raise ValueError('Unexpected lifecycle stream')
        while i<len(lines) and lines[i]!=tag+'_END':i+=1
        if i==len(lines):raise ValueError('Truncated lifecycle frame')
        decoded.append(decoders[tag].decode(lines[start:i+1]));i+=1
        frames.append(dict(stream=tag,full=int(lines[start].split()[4]),denseBytes=len(decoded[-1].encode()),compactBytes=len(('\n'.join(lines[start:i])+'\n').encode())))
    if decoded!=expected:raise ValueError('Lifecycle reconstruction differs from complete native evidence')
    counts={tag:dict(images=d.sequence,full=d.full,reused=d.reused) for tag,d in decoders.items()}
    if any(c!={'images':10,'full':9,'reused':1} for c in counts.values()):raise ValueError('Missing destruction/reconstruction full frames')
    return dict(qualified=False,controlsPassed=True,nativeLifecycle=lifecycle,streams=counts,frames=frames,denseBytes=len(''.join(expected).encode()),compactBytes=(root/'compact.txt').stat().st_size,scope='The unchanged generated C logger replays retained scope metadata, object references and memory metadata through four native destruction/reconstruction cycles at one address. All 30 frames reconstruct exactly, including removal and fresh monotonic identities. This is serialized evidence replay, not a new HDL execution, complete graph teardown or operational board qualification.')


def run(bridge,native,out):
    check(native);native_review(native);out.mkdir(exist_ok=False)
    build=json.loads((bridge/'build.json').read_text())
    if sha(bridge/'icarus_shim.c')!=build['outputs']['icarus_shim.c']:raise ValueError('Changed built logger')
    shim=(bridge/'icarus_shim.c').read_text();a=shim.index('/* Compact only serialized log records.');b=shim.index('static int robotron_scope_metadata_inventory(FILE*out',a)
    (out/'logger.h').write_text(shim[a:b])
    (out/'probe.c').write_text('#define _GNU_SOURCE\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include "logger.h"\nint main(void){char*data=NULL;size_t n=0;FILE*f=open_memstream(&data,&n);if(!f)return 2;int c;while((c=getchar())!=EOF)if(fputc(c,f)==EOF)return 2;if(fclose(f))return 2;int rc=robotron_metadata_log(stdout,"%s",data);free(data);return rc<0?2:0;}\n')
    dense=''.join(images((native/'enabled.stdout').read_text()));(out/'dense.txt').write_text(dense)
    command=['cc','-O2',str(out/'probe.c'),'-o',str(out/'probe')];subprocess.run(command,check=True)
    result=subprocess.run([str((out/'probe').resolve())],input=dense,capture_output=True,text=True,check=True)
    (out/'compact.txt').write_text(result.stdout);(out/'stderr.txt').write_text(result.stderr)
    (out/'run.json').write_text(json.dumps(dict(exitCode=result.returncode,command=command,bridgeBuildSha256=sha(bridge/'build.json'),generatedShimSha256=sha(bridge/'icarus_shim.c'),nativeReceiptSha256=sha(native/'run.json'),nativeOutputSha256=sha(native/'enabled.stdout')),indent=2)+'\n')
    shutil.copytree(native,out/'native')
    for src,dst in [('build.json','bridge-build.json'),('icarus_shim.c','icarus_shim.c')]:shutil.copyfile(bridge/src,out/dst)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('bridge','native','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.bridge,a.native,a.out)
