#!/usr/bin/env python3
"""Pin arithmetic, reduction and concatenation payload ownership."""
import argparse,hashlib,json,tarfile
from pathlib import Path
from thread_board_reachability import ARCHIVE_SHA
from retained_evidence import check
from ttl7406_probe import sha

FAMILIES = {
    'arithmetic': {'vvp_arith_sum', 'vvp_arith_sub', 'vvp_cmp_eq', 'vvp_cmp_eeq', 'vvp_cmp_nee'},
    'reduction': {'vvp_reduce_nor'},
    'concatenation': {'vvp_fun_concat', 'vvp_fun_concat8'},
}


def classify(classes):
    if not classes or any(not isinstance(n,int) or isinstance(n,bool) or n<=0 for n in classes.values()):
        raise ValueError('Invalid native class inventory')
    result={group:{k:v for k,v in classes.items() if k in names} for group,names in FAMILIES.items()}
    known=set().union(*FAMILIES.values())
    result['otherFamilies']={k:v for k,v in classes.items() if k not in known}
    return result


def build(archive,board,out):
    if sha(archive)!=ARCHIVE_SHA:raise ValueError('Changed pinned archive')
    check(board);assessment=json.loads((board/'assessment.json').read_text())
    if not assessment.get('nativeClassBindingsMatchGraph'):raise ValueError('Need bound native class evidence')
    files={}
    with tarfile.open(archive) as tar:
        for name in ('vvp/arith.h','vvp/arith.cc','vvp/reduce.cc','vvp/concat.h','vvp/concat.cc','vvp/vvp_net.cc'):
            members=[m for m in tar.getmembers() if m.name.endswith('/'+name)]
            if len(members)!=1:raise ValueError('Ambiguous source')
            files[name]=tar.extractfile(members[0]).read().decode()
    def section(name,start,end):
        text=files[name];a=text.index(start);b=text.index(end,a+len(start))
        return dict(file=name,firstLine=text[:a].count('\n')+1,excerpt=text[a:b])
    result=dict(qualified=False,
        scope='Pinned expression payload ownership; no native state, fault, continuation or operational qualification.',
        archiveSha256=ARCHIVE_SHA,boardManifestSha256=sha(board/'manifest.json'),
        observed=classify(assessment['nativeClasses']['fun']),
        sources={n:hashlib.sha256(s.encode()).hexdigest() for n,s in files.items()},
        evidence={
            'arithmeticFields':section('vvp/arith.h','class vvp_arith_  :','class vvp_arith_abs'),
            'arithmeticInitializationAndPartialDispatch':section('vvp/arith.cc','vvp_arith_::vvp_arith_(', 'vvp_arith_abs::vvp_arith_abs()'),
            'arithmeticAndEqualityDispatch':section('vvp/arith.cc','vvp_arith_sum::vvp_arith_sum(', 'vvp_cmp_eqx::vvp_cmp_eqx('),
            'partialOperandExpansion':section('vvp/vvp_net.cc','void vvp_net_fun_t::recv_vec4_pv_(', 'void vvp_net_fun_t::recv_vec4_pv('),
            'reductionCacheAndPartialReuse':section('vvp/reduce.cc','class vvp_reduce_base :','class vvp_reduce_and '),
            'reductionNor':section('vvp/reduce.cc','class vvp_reduce_nor ', 'class vvp_reduce_xnor '),
            'concatFields':section('vvp/concat.h','class vvp_fun_concat  :','/* vvp_fun_repeat'),
            'concatDispatch':section('vvp/concat.cc','vvp_fun_concat::vvp_fun_concat(', 'vvp_fun_repeat::vvp_fun_repeat('),
        }, requirements=[
            'Admit exact native classes, not name prefixes or base-class casts alone. Unlisted arithmetic/comparison, reduction and concat subclasses need their own field audit and refusal controls.',
            'Arithmetic retains wid_, both logical operand vectors with their actual widths, and x_val_. Constructor code initializes operands to Z despite the header comment describing X; x_val_ is X. Keep output-width configuration and initialized fallback payload under observation.',
            'Arithmetic partial receives expand a fresh full-width Z vector before dispatch; they do not merge into the previous operand. Sum/subtraction and equality receive paths dispatch synchronously, without a private pending scheduler destination.',
            'Exact/case equality compares X/Z as values; logical equality propagates unknown unless a known mismatch decides the result. Comparisons require equal input widths. Sum and subtraction have distinct short-input padding; qualify actual native behavior rather than silently normalizing it.',
            'Reduction bits_ cannot be discarded as temporary solely from its source comment: full receives overwrite it, but recv_vec4_pv preserves untouched bits and uses prior width. Observe initialized empty storage and subsequent full/partial contents; exercise partial-first, repeated and full-after-partial inputs.',
            'Concat retains four configured widths, the assembled value and a nullable pending destination. A partial write preserves other slices. Bind the adjusted generic-event identity to queued/executing wrappers; run_run clears net_ before downstream dispatch.',
            'Concat4 suppresses unchanged writes; concat8 schedules them when idle. Concat8 retains strengths, and four-state receives convert to strength 6/6. Logical bits alone cannot establish concat8 equivalence; qualify constructor storage before reading it.',
            'Native controls must cover wide vectors, X/Z, both operand ports, partial receives, unchanged-output cache changes, idle/queued/executing concat states and restored faults in each retained field. Refuse unsupported families without partial inventory.',
            'Measure full-scan board cost and exact dense/compact reconstruction before operational integration. Resolver, callback/list contents, storage lifetime and bridge referents remain separate obligations.',
        ])
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('x') as f:json.dump(result,f,indent=2);f.write('\n')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','board','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();build(a.archive,a.board,a.out)
