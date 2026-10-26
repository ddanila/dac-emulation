#!/usr/bin/env python3
"""Verify direct live callback/payload association and restored pointer swaps."""
import argparse,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
from display_payload_probe import snapshot as payload_snapshot
from private_sync_family_probe import snapshot as callback_snapshot
HERE=Path(__file__).resolve().parent


def bundle(lines):
    if lines[0]!='VA_BEGIN' or lines[-1]!='VA_END':raise ValueError('Invalid association bundle')
    cursor=1;sections={}
    for prefix in ('VF','VD','VJ'):
        if not lines[cursor].startswith(prefix+'_BEGIN '):raise ValueError('Missing association section')
        end=lines.index(prefix+'_END',cursor)
        sections[prefix]=lines[cursor:end+1];cursor=end+1
    if cursor!=len(lines)-1:raise ValueError('Unexpected association data')
    callbacks=callback_snapshot(sections['VF']);payload=payload_snapshot(sections['VD']);links={}
    h=sections['VJ'][0].split()
    if len(h)!=3 or h[:2]!=['VJ_BEGIN','1']:raise ValueError('Invalid link header')
    for line in sections['VJ'][1:-1]:
        a=line.split()
        if len(a)!=3 or a[0]!='VJ_LINK':raise ValueError('Invalid association record')
        owner,callback=map(int,a[1:])
        if owner<1 or callback<1 or owner in links or callback in links.values():raise ValueError('Non-unique association')
        links[owner]=callback
    if int(h[2])!=len(links) or set(links)!={o['id'] for o in payload['objects']}:raise ValueError('Unassociated display payload')
    by_id={cb['values'][0]:cb for cb in callbacks['callbacks']}
    if set(links.values())!=set(by_id):raise ValueError('Unassociated fixture callback')
    for obj in payload['objects']:
        cb=by_id[links[obj['id']]];v=cb['values']
        if v[1]!=obj['executing'] or v[2]!=1 or v[3]!=7 or v[4]!=1 or v[6]!=0 or Path(cb['code']['module']).name!='system.vpi':
            raise ValueError('Wrong associated callback state/family')
    return {'callbacks':callbacks,'payload':payload,'links':links}


def review(root):
    baseline=None;faults=observations=released=0
    for name in ('vendor','rebuilt','disabled','enabled','corrupt'):
        text=(root/(name+'.stdout')).read_text()
        if (root/(name+'.stderr')).read_text():raise ValueError('Runtime diagnostic')
        output=[s for s in text.splitlines() if not s.startswith(('VA_','VF_','VD_','VJ_'))]
        if baseline is None:baseline=output
        if output!=baseline:raise ValueError('Changed callback/HDL continuation')
        expected=[line for i,t in enumerate((2,12,22)) for line in (f'FIRST {t}.00 ns b{i}',f'SECOND {t}.00 ns d{i}')]
        if [s for s in output if s.startswith(('FIRST ','SECOND '))]!=expected:raise ValueError('Wrong callback order or deferred values')
        groups=[];current=[]
        for line in text.splitlines():
            if line.startswith('VA_API '):
                if current or line!=f'VA_API {int(name not in ("vendor","rebuilt"))}':raise ValueError('Wrong loaded module')
                groups.append({'shots':[],'fault':None})
            elif line=='VA_BEGIN':
                if current or not groups:raise ValueError('Nested/orphan bundle')
                current=[line]
            elif line=='VA_END':
                if not current:raise ValueError('Orphan bundle end')
                current.append(line);bundle(current);groups[-1]['shots'].append(current);current=[]
            elif line.startswith(('VF_','VD_','VJ_')):
                if not current:raise ValueError('Orphan observer section')
                current.append(line)
            elif line.startswith('VA_FAULT '):
                if current or not groups or groups[-1]['fault'] is not None:raise ValueError('Invalid fault marker')
                groups[-1]['fault']=line
            elif line.startswith('VA_'):raise ValueError('Unknown association record')
        if current or len(groups)!=6:raise ValueError('Incomplete controls')
        for i,g in enumerate(groups):
            shots=g['shots'];fault=g['fault'];enabled=name in ('enabled','corrupt');pending=i%2==0;sequence=i//2+1
            expected_fault=('VA_FAULT payload_unchanged=1 rejected=1 restored=1' if pending else 'VA_FAULT none') if name=='corrupt' else None
            if fault!=expected_fault or len(shots)!=(2+int(name=='corrupt' and pending) if enabled else 0):raise ValueError('Missing fault/observation coverage')
            if not enabled:continue
            if any(s!=shots[0] for s in shots[1:]):raise ValueError('Changed or unrestored associated state')
            state=bundle(shots[0]);payload=state['payload'];callbacks=state['callbacks'];ids=[2*sequence-1,2*sequence] if pending else []
            if list(state['links'])!=ids or list(state['links'].values())!=ids:raise ValueError('Wrong fixture lifetime association')
            if payload['created']!=2*sequence or payload['freed']!=2*sequence-2*int(pending) or payload['format']!=[-9,2,8,0,' ns']:
                raise ValueError('Wrong payload lifetime/format')
            if callbacks['time']!=(2000,12000,22000)[sequence-1]+(0 if pending else 1000) or callbacks['mode']!=3:raise ValueError('Wrong observation boundary')
            for j,obj in enumerate(payload['objects']):
                if obj['executing'] or obj['nitems']!=3 or obj['destination']!=1 or obj['name']!='$strobe' or obj['scope']!='probe':raise ValueError('Changed display metadata')
                items=obj['items'];fmt=('FIRST','SECOND')[j]+' %0t %h'
                if int(items[0]['value'],2)!=int.from_bytes(fmt.encode(),'big') or int(items[1]['value'],2)!=(2,12,22)[sequence-1] or items[2]['value']!=f'{(0xa0,0xc0)[j]+sequence-1:08b}':raise ValueError('Changed associated argument values')
                observations+=1
            if not pending:released+=1
            if name=='corrupt' and pending:faults+=1
    if (faults,observations,released)!=(3,12,6):raise ValueError('Incomplete association coverage')
    return {'completed':True,'qualified':False,'vendorAndRebuiltOutputExactlyEqual':True,'observerOutputExactlyEqual':True,
            'payloadPointerSwapsRejectedAndRestored':faults,'associatedPayloadObservations':observations,'releasedAssociationObservations':released,
            'payloadValuesUnchangedDuringRejectedSwap':True,
            'scope':'Direct callback handle, registered function and user-data identity linked to typed strobe payloads in a standalone fixture.',
            'notEstablished':['Board integration and long-window controls','Other callback families and referenced state','Executing scheduler wrappers, freed storage and general rollback']}


def run(build,runtime,modules,out):
    build=build.resolve();runtime=runtime.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    receipt=json.loads((build/'build.json').read_text())
    for n,h in receipt['outputs'].items():
        if sha(build/n)!=h:raise ValueError('Changed module build')
    for ext in ('c','v'):shutil.copyfile(HERE/f'fixtures/display_association_probe.{ext}',out/f'probe.{ext}')
    subprocess.run(['iverilog','-g2012','-o',str(out/'probe.vvp'),str(out/'probe.v')],check=True)
    flags=['-bundle','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC']
    subprocess.run(['cc',*flags,'-I'+str(build),'-o',str(out/'probe.vpi'),str(out/'probe.c')],check=True)
    vendor=modules/'system.vpi';original=(out/'probe.vvp').read_text();old=':vpi_module "'+str(vendor)+'";'
    if original.count(old)!=1:raise ValueError('Unexpected compiled system module')
    paths=[runtime/'vvp/vvp',runtime/'vvp/libvvp.so',build/'baseline/system.vpi',build/'vpi/system.vpi',out/'probe.vpi',*modules.glob('*.vpi')]
    pins={str(p):sha(p) for p in paths};commands={}
    for name,module,mode in [('vendor',vendor,'off'),('rebuilt',build/'baseline/system.vpi','off'),('disabled',build/'vpi/system.vpi','off'),('enabled',build/'vpi/system.vpi','on'),('corrupt',build/'vpi/system.vpi','corrupt')]:
        (out/(name+'.vvp')).write_text(original.replace(old,':vpi_module "'+str(module)+'";'))
        env=dict(os.environ,K7658_DISPLAY_MODULE=str(module),K7658_DISPLAY_PROBE=mode)
        env['DYLD_LIBRARY_PATH' if platform.system()=='Darwin' else 'LD_LIBRARY_PATH']=str(runtime/'vvp')
        command=[str(runtime/'vvp/vvp'),'-M'+str(modules),'-M.','-mprobe',name+'.vvp'];commands[name]=command
        result=subprocess.run(command,cwd=out,env=env,capture_output=True,text=True,timeout=30)
        (out/(name+'.stdout')).write_text(result.stdout);(out/(name+'.stderr')).write_text(result.stderr);result.check_returncode()
    if any(sha(Path(p))!=h for p,h in pins.items()):raise ValueError('Changed runtime module')
    result=review(out);result.update(runtime=pins,commands=commands,buildReceiptSha256=sha(build/'build.json'),
        sources={n:sha(HERE/n) for n in ('display_association_probe.py','fixtures/display_association_probe.c','fixtures/display_association_probe.v','build_display_association.py','engine-patches/icarus-display-observer.patch','engine-patches/icarus-display-payload-link.patch','engine-patches/icarus-callback-payload-link.patch','build_private_queue_observer.py','display_payload_probe.py','private_sync_family_probe.py')})
    result['sources'].update(receipt['sources'])
    shutil.copyfile(build/'build.json',out/'build.json');(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'assessment.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('build','runtime','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        result=review(a.check);retained=json.loads((a.check/'assessment.json').read_text())
        if any(retained.get(k)!=v for k,v in result.items()):raise ValueError('Changed assessment')
        print('Callback/payload association controls verified; board and general rollback remain open.')
    else:
        if any(x is None for x in (a.build,a.runtime,a.modules,a.out)):p.error('Need build, runtime, modules and out')
        run(a.build,a.runtime,a.modules,a.out)
