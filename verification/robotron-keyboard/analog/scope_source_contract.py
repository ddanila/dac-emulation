#!/usr/bin/env python3
"""Extract pinned scope ownership semantics before implementing state controls."""
import argparse
import hashlib
import json
import tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA, analyze
from ttl7406_probe import sha


def build(archive, vvp, out):
    if sha(archive) != ARCHIVE_SHA:
        raise ValueError('Changed pinned Icarus archive')
    sources = {}
    with tarfile.open(archive) as tar:
        for name in ('vvp/vpi_scope.cc', 'vvp/vpi_priv.h', 'vvp/vthread.cc'):
            matches = [m for m in tar.getmembers() if m.name.endswith('/' + name)]
            if len(matches) != 1:
                raise ValueError('Ambiguous native source: ' + name)
            sources[name] = tar.extractfile(matches[0]).read().decode()

    def section(name, start, end):
        text = sources[name]
        a = text.index(start)
        b = text.index(end, a + len(start))
        return dict(file=name, firstLine=text[:a].count('\n') + 1, excerpt=text[a:b])

    program = analyze(vvp.read_text())
    result = dict(
        qualified=False,
        scope='Pinned source semantics and compiled scope profile; not native scope observation or rollback qualification.',
        archiveSha256=ARCHIVE_SHA,
        compiled=dict(sha256=sha(vvp), scopes=program['scopes'],
                      disableInstructions={k: v for k, v in program['opcodeCounts'].items() if k.startswith('%disable')}),
        sources={n: hashlib.sha256(s.encode()).hexdigest() for n, s in sources.items()},
        evidence={
            'scopeFields': section('vvp/vpi_priv.h', 'class __vpiScope :', 'class vpiScopeFunction'),
            'constructorOnlyInitializesNamesAndAutomaticFlag': section('vvp/vpi_scope.cc', '__vpiScope::__vpiScope(', 'int __vpiScope::vpi_get('),
            'hierarchyAttachment': section('vvp/vpi_scope.cc', 'void vpip_attach_to_scope(', '/*\n * When the compiler encounters'),
            'declarationInitializesFieldsAndAttachesHierarchy': section('vvp/vpi_scope.cc', 'void\ncompile_scope_decl(', 'void compile_scope_recall('),
            'threadCreationAddsMembership': section('vvp/vthread.cc', 'vthread_t vthread_new(', '#ifdef CHECK_WITH_VALGRIND'),
            'reapRemovesMembershipBeforePossibleDeferredDeletion': section('vvp/vthread.cc', 'static void vthread_reap(', 'void vthread_delete('),
            'disableRemovesMembership': section('vvp/vthread.cc', 'static bool do_disable(', 'bool of_DISABLE('),
            'disableConsumesActualMembership': section('vvp/vthread.cc', 'bool of_DISABLE(', '/*\n * Similar to `of_DISABLE`'),
        },
        requirements=[
            'Enumerate the complete compiled scope hierarchy, including empty scopes, and bind each scope to its actual parent and type.',
            'Observe actual scope->threads membership independently of live-thread parent_scope. Reaped or disabled threads can remain live after membership removal.',
            'Resolve membership entries through registered live-thread identities before dereferencing. Validate each member belongs to the recorded scope; do not require every live thread to remain a member.',
            'Observe only fully initialized scopes after declaration completes. Constructor completion alone does not initialize scope pointers, source fields, time units or context fields.',
            'For the static board profile, fail closed on automatic scopes or unexpected context state. Automatic-context support requires separate enumeration and lifecycle controls.',
            'Inject and restore actual membership removal while paused, then require exact internal-state restoration and unchanged firmware/output continuation.',
            'Native fixtures must exercise empty scopes, creation, ordinary completion, disabled pending zombies and callback-driven deferred deletion. Preserve unsupported-profile refusal controls.',
            'A scope hierarchy and thread membership observer does not cover intern object contents, classes, automatic hooks, net/array/fanout state, code operands or freed storage.',
        ])
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'vvp', 'out'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.archive, args.vvp, args.out)
