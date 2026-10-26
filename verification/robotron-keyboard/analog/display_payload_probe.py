#!/usr/bin/env python3
"""Match typed display-payload observation against rebuilt and vendor modules."""
import argparse,copy,json,os,platform,shutil,subprocess
from pathlib import Path
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


def decoded(value):
    if value=='null':return None
    if not value.startswith('hex:'):raise ValueError('Invalid encoded string')
    return bytes.fromhex(value[4:]).decode()


def snapshot(lines):
    h=lines[0].split()
    if len(h)!=5 or h[:2]!=['VD_BEGIN','1'] or lines[-1]!='VD_END':raise ValueError('Invalid display snapshot')
    created,freed,count=map(int,h[2:]);objects=[];fmt=None
    if min(created,freed,count)<0 or created-freed!=count:raise ValueError('Invalid registry lifecycle')
    for line in lines[1:-1]:
        a=line.split()
        if a[0]=='VD_FORMAT':
            if fmt is not None or objects or len(a)!=6:raise ValueError('Invalid format record')
            fmt=[*map(int,a[1:5]),decoded(a[5])]
        elif a[0]=='VD_INFO':
            if fmt is None or len(a)!=12:raise ValueError('Invalid display object')
            ident,executing,lineno,default,destination,nitems=map(int,a[1:7])
            if not 1<=ident<=created or (objects and ident<=objects[-1]['id']) or executing not in (0,1) or lineno<1 or nitems<0 or destination<0:
                raise ValueError('Invalid display object fields')
            objects.append({'id':ident,'executing':executing,'line':lineno,'defaultFormat':default,'destination':destination,
                'nitems':nitems,'name':decoded(a[7]),'filename':decoded(a[8]),'scope':decoded(a[9]),
                'timeUnit':int(a[10]),'timePrecision':int(a[11]),'items':[]})
        elif a[0]=='VD_ITEM':
            if not objects or len(a)!=8:raise ValueError('Invalid display argument')
            ident,ordinal,typ,size,signed=map(int,a[1:6]);obj=objects[-1]
            if ident!=obj['id'] or ordinal!=len(obj['items']) or size<1 or signed not in (0,1):raise ValueError('Invalid argument identity/shape')
            if a[6]=='bits':
                value=decoded(a[7])
                if value is None or len(value)!=size or any(c not in '01xz' for c in value):raise ValueError('Invalid argument bit vector')
            elif a[6]=='real':value=float.fromhex(a[7])
            else:raise ValueError('Unsupported argument encoding')
            obj['items'].append({'type':typ,'size':size,'signed':signed,'encoding':a[6],'value':value})
        else:raise ValueError('Unknown payload record')
    if fmt is None or len(objects)!=count or any(len(o['items'])!=o['nitems'] for o in objects):raise ValueError('Incomplete payload inventory')
    return {'created':created,'freed':freed,'format':fmt,'objects':objects}


def review(root):
    baseline=None;faults=observed=empty=0
    source=(root/'probe.v').read_text().splitlines()
    strobe_lines=[i+1 for i,line in enumerate(source) if '$strobe(' in line]
    if len(strobe_lines)!=1:raise ValueError('Changed strobe fixture')
    for name in ('vendor','rebuilt','disabled','enabled','corrupt'):
        text=(root/(name+'.stdout')).read_text()
        if (root/(name+'.stderr')).read_text():raise ValueError('Runtime diagnostic')
        output=[s for s in text.splitlines() if not s.startswith('VD_')]
        if baseline is None:baseline=output
        if output!=baseline:raise ValueError('Changed display/HDL output')
        expected=[f'STROBE {t}.00 ns b{i} 1.25' for i,t in enumerate((2,12,22))]
        if [s for s in output if s.startswith('STROBE ')]!=expected:raise ValueError('Missing strobe or deferred argument update')
        groups=[];current=[]
        for line in text.splitlines():
            if line.startswith('VD_API '):
                if line!=f'VD_API {int(name not in ("vendor","rebuilt"))}' or current:raise ValueError('Wrong loaded module')
                groups.append({'shots':[],'fault':None})
            elif line.startswith('VD_BEGIN '):
                if not groups or current:raise ValueError('Nested/orphan snapshot')
                current=[line]
            elif line=='VD_END':
                if not current:raise ValueError('Orphan end')
                current.append(line);snapshot(current);groups[-1]['shots'].append(current);current=[]
            elif line.startswith(('VD_FORMAT ','VD_INFO ','VD_ITEM ')):
                if not current:raise ValueError('Orphan payload')
                current.append(line)
            elif line.startswith('VD_FAULT '):
                if not groups or current or groups[-1]['fault'] is not None:raise ValueError('Invalid fault marker')
                groups[-1]['fault']=int(line.split()[1])
            elif line.startswith('VD_'):raise ValueError('Unknown observer record')
        if current or len(groups)!=6:raise ValueError('Missing observations')
        for i,g in enumerate(groups):
            shots=g['shots'];fault=g['fault'];enabled=name in ('enabled','corrupt');pending=i%2==0
            if fault!=(int(pending) if name=='corrupt' else None) or len(shots)!=(2+2*(fault==1) if enabled else 0):raise ValueError('Incomplete mutation controls')
            if not enabled:continue
            if shots[0]!=shots[1]:raise ValueError('Observation changed payload')
            state=snapshot(shots[0]);sequence=i//2+1
            if state['created']!=sequence or state['freed']!=sequence-int(pending) or len(state['objects'])!=int(pending):raise ValueError('Wrong allocation/release lifecycle')
            if state['format']!=[-9,2,8,0,' ns']:raise ValueError('Changed global time format')
            if pending:
                obj=state['objects'][0];items=obj['items']
                if obj['id']!=sequence or obj['line']!=strobe_lines[0] or obj['defaultFormat']!=3 or obj['executing'] or obj['destination']!=1 or obj['nitems']!=4 or obj['name']!='$strobe' or obj['scope']!='probe' or (obj['timeUnit'],obj['timePrecision'])!=(-9,-12) or not obj['filename'].endswith('/probe.v'):
                    raise ValueError('Changed typed payload metadata')
                if [item['type'] for item in items]!=[7,56,48,41] or [item['encoding'] for item in items]!=['bits','bits','bits','real']:
                    raise ValueError('Changed fixture argument types')
                fmt='STROBE %0t %h %0.2f'
                if int(items[0]['value'],2)!=int.from_bytes(fmt.encode(),'big') or int(items[1]['value'],2)!=(2,12,22)[sequence-1] or items[2]['value']!=f'{0xa0+sequence-1:08b}' or items[3]['value']!=1.25:
                    raise ValueError('Changed deferred argument values')
                observed+=1
            else:empty+=1
            if fault:
                altered=snapshot(shots[2]);restored=snapshot(shots[3]);expected=copy.deepcopy(state);expected['objects'][0]['destination']^=1
                if altered!=expected or restored!=state:raise ValueError('Wrong or unrestored payload mutation')
                faults+=1
    if (faults,observed,empty)!=(3,6,6):raise ValueError('Incomplete payload coverage')
    return {'completed':True,'qualified':False,'vendorAndRebuiltOutputExactlyEqual':True,'observerOutputExactlyEqual':True,
            'destinationMutationsDetectedAndRestored':faults,'pendingPayloadObservations':observed,'releasedRegistryObservations':empty,
            'deferredArgumentsFollowNonblockingAssignments':True,
            'scope':'Typed strobe metadata, format, supported argument values and referent-identity checks in a standalone fixture.',
            'notEstablished':['Board integration and callback-to-payload association','Arbitrary VPI objects or monitor callbacks','File descriptor internals','Freed storage contents, executing wrapper state and general rollback']}


def run(build,runtime,modules,out):
    build=build.resolve();runtime=runtime.resolve();modules=modules.resolve();out=out.resolve();out.mkdir(exist_ok=False)
    receipt=json.loads((build/'build.json').read_text())
    for n,h in receipt['outputs'].items():
        if sha(build/n)!=h:raise ValueError('Changed module build')
    for ext in ('c','v'):shutil.copyfile(HERE/f'fixtures/display_payload_probe.{ext}',out/f'probe.{ext}')
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
        sources={n:sha(HERE/n) for n in ('display_payload_probe.py','fixtures/display_payload_probe.c','fixtures/display_payload_probe.v','build_display_observer.py','engine-patches/icarus-display-observer.patch','build_private_queue_observer.py')})
    shutil.copyfile(build/'build.json',out/'build.json');(out/'assessment.json').write_text(json.dumps(result,indent=2)+'\n');print(out/'assessment.json')


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--check',type=Path)
    for n in ('build','runtime','modules','out'):p.add_argument('--'+n,type=Path)
    a=p.parse_args()
    if a.check:
        result=review(a.check);retained=json.loads((a.check/'assessment.json').read_text())
        if any(retained.get(k)!=v for k,v in result.items()):raise ValueError('Changed assessment')
        print('Typed display controls verified; board and general rollback remain open.')
    else:
        if any(x is None for x in (a.build,a.runtime,a.modules,a.out)):p.error('Need build, runtime, modules and out')
        run(a.build,a.runtime,a.modules,a.out)
