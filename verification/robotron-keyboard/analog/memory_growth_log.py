#!/usr/bin/env python3
"""Replay native memory growth through the existing generated compact logger."""
import argparse,json,shutil
from pathlib import Path
import memory_log_replay as original
from memory_growth import review as growth_review
from memory_metadata import parse
from retained_evidence import check
from ttl7406_probe import sha


def images(text):
    lines=text.splitlines();result=[];i=0
    while i<len(lines):
        if lines[i].startswith('VMM_BEGIN '):
            start=i
            while i<len(lines) and not lines[i].startswith('VMM_END '):i+=1
            if i==len(lines):raise ValueError('Missing native growth footer')
            result.append('\n'.join(lines[start:i+1])+'\n')
        i+=1
    return result


def review(root):
    native=root/'native';check(native);growth=growth_review(native)
    receipt=json.loads((root/'run.json').read_text());build=json.loads((root/'bridge-build.json').read_text())
    if sha(root/'bridge-build.json')!=receipt['bridgeBuildSha256'] or sha(root/'icarus_shim.c')!=receipt['generatedShimSha256'] or receipt['generatedShimSha256']!=build['outputs']['icarus_shim.c']:raise ValueError('Changed built logger identity')
    if sha(native/'run.json')!=receipt['nativeReceiptSha256'] or sha(native/'enabled.stdout')!=receipt['nativeOutputSha256']:raise ValueError('Changed native growth identity')
    shim=(root/'icarus_shim.c').read_text();a=shim.index('/* Compact only serialized log records.');b=shim.index('static int robotron_scope_metadata_inventory(FILE*out',a)
    if (root/'logger.h').read_text()!=shim[a:b]:raise ValueError('Logger differs from built bridge')
    dense=images((native/'enabled.stdout').read_text());counts=[len(parse(text.splitlines())['rows']) for text in dense]
    if counts!=[1,2,2,3,3,3,4,4,5,5] or ''.join(dense)!=(root/'dense.txt').read_text():raise ValueError('Missing exact growing native images')
    result=original.review(root)
    if result['images']!=10 or result['fullImages']!=5 or result['reusedImages']!=5:raise ValueError('Wrong growth full/reuse coverage')
    result['nativeGrowth']=growth;result['memoryCounts']=counts
    frames=(root/'compact.txt').read_text().split('VMMD_END\n')[:-1]
    result['frames']=[dict(memories=count,full=frame.splitlines()[0].split()[4]=='1',denseBytes=len(image.encode()),compactBytes=len((frame+'VMMD_END\n').encode())) for count,image,frame in zip(counts,dense,frames)]
    if len(result['frames'])!=10:raise ValueError('Missing growth frame costs')
    result['scope']='The unchanged C logger extracted from the pinned built bridge encodes ten retained native memory metadata inventories growing from one to five objects. Five complete frames and five unchanged-body reuse frames reconstruct every metadata byte, including new identities and bounded names. Array payload/cache compactness is separately tested by memory_growth_compact.py. This replay does not claim a new HDL execution, destruction/reuse, or operational board cost.'
    return result


def run(bridge,native,out):
    check(native);growth_review(native);original.run(bridge,native,out)
    shutil.copytree(native,out/'native')
    for src,dst in [('build.json','bridge-build.json'),('icarus_shim.c','icarus_shim.c')]:shutil.copyfile(bridge/src,out/dst)
    (out/'assessment.json').write_text(json.dumps(review(out),indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('bridge','native','out'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();run(a.bridge,a.native,a.out)
