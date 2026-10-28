#!/usr/bin/env python3
"""Refuse all native inventory entry points once final cleanup begins."""
import argparse,json,re
from pathlib import Path
import build_native_teardown_board_runtime as previous
from ttl7406_probe import sha

def guard(out):
    p=out/'vvp/lib_main.cc';s=p.read_text();old='static void final_cleanup()\n{'
    if s.count(old)!=1:raise ValueError('Ambiguous final cleanup boundary')
    s=s.replace(old,'''// Observation belongs to a live simulator and is permanently closed before
// any native destruction. This does not authorize concurrent observation.
static bool robotron_observation_active=true;
extern "C" int robotron_vvp_observation_active(){return robotron_observation_active;}
static void final_cleanup()
{
      robotron_observation_active=false;''');p.write_text(s)
    pattern=re.compile(r'(extern\s+"C"\s+int\s+(robotron_vvp_\w*inventory)\s*\([^{};]*\)\s*\{)')
    sites={}
    for p in sorted((out/'vvp').glob('*.cc')):
        text=p.read_text();names=[]
        def add(match):
            names.append(match[2]);return match[1]+'\n    if(!robotron_vvp_observation_active())return -1;\n'
        text=pattern.sub(add,text)
        if names:
            p.write_text('extern "C" int robotron_vvp_observation_active();\n'+text);sites[str(p.relative_to(out))]=names
    if sum(map(len,sites.values()))<52:raise ValueError('Incomplete native inventory guard enumeration')
    (out/'observer-shutdown-sites.json').write_text(json.dumps(sites,indent=2)+'\n')

def build(archive,out,bison,jobs):
    out=out.resolve();base=previous.previous.previous.previous.base;original=base.subprocess
    class Commands:
        def __getattr__(self,name):return getattr(original,name)
        def run(self,command,**kwargs):
            if command[:3]==['make','-C','vvp']:guard(out)
            return original.run(command,**kwargs)
    try:base.subprocess=Commands();previous.build(archive,out,bison,jobs)
    finally:base.subprocess=original
    r=json.loads((out/'build.json').read_text());r['sources'][Path(__file__).name]=sha(Path(__file__))
    sites=json.loads((out/'observer-shutdown-sites.json').read_text())
    r['outputs'].update({n:sha(out/n) for n in [*sites,'vvp/lib_main.cc','observer-shutdown-sites.json']})
    r['observerShutdown']='Every exported int-returning robotron_vvp_*inventory definition refuses with -1 before touching output or registries once final_cleanup begins. This is a lifecycle guard, not a registry-clearing claim, runtime reuse, general getter/mutator safety, or concurrent-observation support.'
    (out/'build.json').write_text(json.dumps(r,indent=2)+'\n')

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('archive','out','bison'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--jobs',type=int,default=2);a=p.parse_args();build(a.archive,a.out,a.bison,a.jobs)
