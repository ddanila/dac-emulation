#!/usr/bin/env python3
"""Replay native parameter growth through the existing generated compact logger."""
import argparse,json,shutil
from pathlib import Path
import parameter_log_replay as original
from parameter_growth import review as growth_review
from parameter_payload import parse
from retained_evidence import check
from ttl7406_probe import sha


def images(text):
    lines=text.splitlines();result=[];i=0
    while i<len(lines):
        if lines[i].startswith('VPM_BEGIN '):
            start=i
            while i<len(lines) and not lines[i].startswith('VPM_END '):i+=1
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
    if counts!=[4,5,6,7,7,8,9,10] or ''.join(dense)!=(root/'dense.txt').read_text():raise ValueError('Missing exact growing native images')
    result=original.review(root)
    if result['images']!=8 or result['fullImages']!=7 or result['reusedImages']!=1:raise ValueError('Wrong growth full/reuse coverage')
    result['nativeGrowth']=growth;result['parameterCounts']=counts
    frames=(root/'compact.txt').read_text().split('VPMD_END\n')[:-1]
    result['frames']=[dict(parameters=count,full=frame.splitlines()[0].split()[4]=='1',denseBytes=len(image.encode()),compactBytes=len((frame+'VPMD_END\n').encode())) for count,image,frame in zip(counts,dense,frames)]
    if len(result['frames'])!=8 or any(f['compactBytes']<=f['denseBytes'] for f in result['frames'] if f['full']):raise ValueError('Missing measured full-frame growth overhead')
    result['scope']='The unchanged C logger extracted from the pinned built bridge encodes eight retained native parameter inventories growing from four to ten objects. Seven complete frames and one unchanged-body reuse reconstruct every native byte, including new IDs, wide unknown bits, real storage and embedded-null strings. Growth can expand output beyond dense images. This replay does not claim a new HDL execution, unsupported late-family admission, destruction/reuse, or operational board cost.'
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
