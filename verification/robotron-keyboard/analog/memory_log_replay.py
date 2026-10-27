#!/usr/bin/env python3
"""Exercise the built bridge's exact C logger on retained changing native memorys."""
import argparse,json,subprocess
from pathlib import Path
from ttl7406_probe import sha
from memory_compact import MemoryDecoder


def review(root):
    expected=(root/'dense.txt').read_text();lines=(root/'compact.txt').read_text().splitlines();decoder=MemoryDecoder();dense=[];i=0
    while i<len(lines):
        a=i
        while i<len(lines) and lines[i]!='VMMD_END':i+=1
        if i==len(lines):raise ValueError('Truncated memory replay')
        dense.append(decoder.decode(lines[a:i+1]));i+=1
    if ''.join(dense)!=expected or decoder.full<2 or not decoder.reused:raise ValueError('Changing/full/reused payload reconstruction differs')
    receipt=json.loads((root/'run.json').read_text())
    if receipt['exitCode'] or (root/'stderr.txt').read_text():raise ValueError('Native logger failed')
    return dict(qualified=False,controlsPassed=True,images=decoder.sequence,fullImages=decoder.full,reusedImages=decoder.reused,denseBytes=len(expected.encode()),compactBytes=(root/'compact.txt').stat().st_size,
        scope='Exact C logger extracted from the built combined bridge encodes retained native name-byte changes and restoration. Every decoded byte matches its full native image. This is logger replay, not a new HDL execution or operational memory/cost bound.')


def run(bridge,native,out):
    out.mkdir(exist_ok=False);build=json.loads((bridge/'build.json').read_text())
    if sha(bridge/'icarus_shim.c')!=build['outputs']['icarus_shim.c']:raise ValueError('Changed generated logger source')
    text=(bridge/'icarus_shim.c').read_text();a=text.index('/* Compact only serialized log records.');b=text.index('static int robotron_scope_metadata_inventory(FILE*out',a)
    logger=text[a:b];(out/'logger.h').write_text(logger)
    source='#define _GNU_SOURCE\n#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include "logger.h"\nint main(void){char*data=NULL;size_t n=0;FILE*f=open_memstream(&data,&n);if(!f)return 2;int c;while((c=getchar())!=EOF)if(fputc(c,f)==EOF)return 2;if(fclose(f))return 2;int rc=robotron_metadata_log(stdout,"%s",data);free(data);return rc<0?2:0;}\n'
    (out/'probe.c').write_text(source)
    native_text=(native/'enabled.stdout').read_text();lines=native_text.splitlines();dense=[];i=0
    while i<len(lines):
        if lines[i].startswith('VMM_BEGIN '):
            a=i
            while i<len(lines) and not lines[i].startswith('VMM_END '):i+=1
            if i==len(lines):raise ValueError('Missing native memory footer')
            dense.append('\n'.join(lines[a:i+1])+'\n')
        i+=1
    (out/'dense.txt').write_text(''.join(dense));cmd=['cc','-O2',str(out/'probe.c'),'-o',str(out/'probe')];subprocess.run(cmd,check=True)
    r=subprocess.run([str((out/'probe').resolve())],input=''.join(dense),capture_output=True,text=True,check=True)
    (out/'compact.txt').write_text(r.stdout);(out/'stderr.txt').write_text(r.stderr)
    (out/'run.json').write_text(json.dumps(dict(exitCode=r.returncode,command=cmd,bridgeBuildSha256=sha(bridge/'build.json'),generatedShimSha256=sha(bridge/'icarus_shim.c'),nativeReceiptSha256=sha(native/'run.json'),nativeOutputSha256=sha(native/'enabled.stdout')),indent=2)+'\n')
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('bridge','native','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.bridge,a.native,a.out)
