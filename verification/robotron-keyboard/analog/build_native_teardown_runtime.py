#!/usr/bin/env python3
"""Build actual final cleanup with AddressSanitizer; Valgrind annotations are disabled."""
import argparse,json,re
from pathlib import Path
import build_parameter_refusal_cycle_runtime as previous
import build_display_association as base
from ttl7406_probe import sha
ANNOTATIONS=r'''/* Teardown-only compatibility header, NOT a Valgrind implementation.
 * Native CHECK_WITH_VALGRIND cleanup is enabled. Allocation annotations are
 * explicitly disabled; AddressSanitizer instruments real allocations instead.
 */
#ifndef ROBOTRON_TEARDOWN_ANNOTATIONS_H
#define ROBOTRON_TEARDOWN_ANNOTATIONS_H
#include <stdio.h>
#define RUNNING_ON_VALGRIND 0
#define VALGRIND_MAKE_MEM_NOACCESS(a,b) do { (void)(a); (void)(b); } while(0)
#define VALGRIND_CREATE_MEMPOOL(a,b,c) do { (void)(a); (void)(b); (void)(c); } while(0)
#define VALGRIND_MEMPOOL_ALLOC(a,b,c) do { (void)(a); (void)(b); (void)(c); } while(0)
#define VALGRIND_MEMPOOL_FREE(a,b) do { (void)(a); (void)(b); } while(0)
#define VALGRIND_DESTROY_MEMPOOL(a) do { (void)(a); } while(0)
#define VALGRIND_PRINTF(...) fprintf(stderr,__VA_ARGS__)
#endif
'''


def build(archive,out,bison,jobs):
    out=out.resolve();original=base.subprocess
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            if command[0]=='./configure':
                header=out/'teardown-annotations/valgrind/memcheck.h';header.parent.mkdir(parents=True);header.write_text(ANNOTATIONS)
                flags='-g -O1 -fsanitize=address -fno-omit-frame-pointer'
                command.extend(['--with-valgrind','CPPFLAGS=-I'+str(out/'teardown-annotations'),'CFLAGS='+flags,'CXXFLAGS='+flags,'LDFLAGS=-fsanitize=address'])
            return original.run(command,**kwargs)
    try:base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:base.subprocess=original
    finalize(out)


def finalize(out):
    config=(out/'config.h').read_text()
    if not re.search(r'^#\s*define\s+CHECK_WITH_VALGRIND\s+1\s*$',config,re.M):raise ValueError('Native teardown was not enabled')
    if (out/'teardown-annotations/valgrind/memcheck.h').read_text()!=ANNOTATIONS:raise ValueError('Changed annotation header')
    for name in ('vvp/Makefile','vpi/Makefile'):
        if '-fsanitize=address' not in (out/name).read_text():raise ValueError('Missing sanitizer flags')
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    r['outputs'].update({n:sha(out/n) for n in ('config.h','vvp/Makefile','vpi/Makefile','vvp/lib_main.cc','teardown-annotations/valgrind/memcheck.h')})
    r['scope']='Actual native CHECK_WITH_VALGRIND final cleanup is enabled with explicitly disabled Valgrind client annotations. Runtime and VPI modules use AddressSanitizer. This is not a Valgrind run, leak proof, custom-pool access check, or teardown qualification until execution and diagnostics are reviewed.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
