#!/usr/bin/env python3
"""Retain pinned compiler grammar and native vector-handle creation evidence."""
import argparse,hashlib,json,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from ttl7406_probe import sha


def assess(archive):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed compiler archive')
    paths=('vvp/parse.y','vvp/words.cc','vvp/vpi_signal.cc');sources={}
    with tarfile.open(archive) as tar:
        for path in paths:
            found=[m for m in tar.getmembers() if m.name.endswith('/'+path)]
            if len(found)!=1:raise ValueError('Missing compiler source')
            sources[path]=tar.extractfile(found[0]).read().decode()
    def section(path,start,end):
        text=sources[path];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=path,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    evidence=dict(localFlag=section('vvp/parse.y','\nlocal_flag\n','\nlabel_opt\n'),grammar=section('vvp/parse.y','  | T_LABEL K_VAR local_flag','  | T_LABEL K_NET_R local_flag'),
        variableCreation=section('vvp/words.cc','void compile_variable(','vvp_net_t* create_constant_node('),
        netCreation=section('vvp/words.cc','static void do_compile_net(','static void __compile_net('),
        nativeClasses=section('vvp/vpi_signal.cc','struct signal_reg :','struct signal_byte :'))
    return dict(qualified=False,completed=True,archiveSha256=ARCHIVE_SHA,nativeSources={n:hashlib.sha256(t.encode()).hexdigest() for n,t in sources.items()},evidence=evidence,
        findings=['The grammar passes signedness and declaration ranges into vector constructors; .var/i selects a signed integer handle.',
            'compile_variable and do_compile_net construct and attach VPI handles only when local_flag is false. The net functor can still exist independently of a VPI handle.',
            'signal_reg, signal_integer and signal_net return distinct VPI type codes. The metadata join must preserve their exact native family.'],
        scope='Selected compiler-source evidence for visible vector declaration matching. This is not a general grammar admission proof or exclusion of later writes.')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archive',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();a.out.write_text(json.dumps(assess(a.archive),indent=2)+'\n')
