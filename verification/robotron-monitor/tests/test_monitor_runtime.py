"""Pinned runtime provenance and rollback-sensitive experimental comparator checks."""
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import monitor_runtime as runtime
import solver_profile
import controller_history
import lab
import test_controller


class RuntimeProvenanceTests(unittest.TestCase):
    def test_receipt_names_the_configured_compiler(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            for name in ('bin/ngspice','lib/ngspice/analog.cm',
                         'share/ngspice/scripts/spinit'):
                path=root/'install'/name;path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(b'fixture')
            with patch.dict(os.environ,{'CC':'/opt/homebrew/bin/gcc-16',
                                       'CXX':'/opt/homebrew/bin/g++-16'}),\
                 patch.object(runtime.subprocess,'check_output',side_effect=[
                     'gcc (GCC) 16.2.0\n','g++ (GCC) 16.2.0\n',
                     'ngspice-47\n']) as checked:
                record=runtime.receipt(root)
            self.assertEqual(record['compiler_command'],['/opt/homebrew/bin/gcc-16'])
            self.assertEqual(record['cxx_command'],['/opt/homebrew/bin/g++-16'])
            self.assertIn('gcc (GCC)',record['compiler'])
            self.assertIn('g++ (GCC)',record['cxx_compiler'])
            self.assertEqual(checked.call_args_list[0].args[0],
                             ['/opt/homebrew/bin/gcc-16','--version'])

    def test_hashes_configuration_and_required_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();files={}
            for name in ('bin/ngspice','lib/ngspice/analog.cm','share/ngspice/scripts/spinit'):
                p=root/'install'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b'fixture')
                files['install/'+name]=runtime.digest(p)
            data=dict(format='dac-monitor-runtime-v1',archive_sha256=runtime.ARCHIVE_SHA256,
                install_prefix=str(root/'install'),inputs=runtime.inputs(),configure_flags=runtime.FLAGS,files=files)
            def save(d): (root/'runtime.json').write_text(json.dumps(d))
            save(data);self.assertEqual(runtime.verify(root)[0],root/'install/bin/ngspice')
            for change in ({'inputs':{}},{'configure_flags':[]},{'files':{'install/bin/ngspice':files['install/bin/ngspice']}}):
                save(data|change)
                with self.assertRaises(ValueError):runtime.verify(root)
            save(data);(root/'install/lib/ngspice/analog.cm').write_bytes(b'changed')
            with self.assertRaises(ValueError):runtime.verify(root)

    def test_wrong_archive_rejected_before_creating_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);archive=root/'wrong.tar.gz';archive.write_bytes(b'not the source')
            with self.assertRaises(ValueError):runtime.build(archive,root/'output')
            self.assertFalse((root/'output').exists())

    def test_windowed_audit_does_not_count_proposals_as_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'log'
            p.write_text('progress\rCRT_TRUNC BJT name=q1 t=0x1p-10 from=inf to=0x1p-20\n'
                'CRT_TRUNC IND name=l1 t=0x1p-10 from=0x1p-20 to=0x1p-21\n'
                'CRT_STEP reject_lte t=0x1p-10 dt=0x1p-19 target=0x1p-21\n'
                'CRT_STEP accept t=0x1p-11 next_dt=0x1p-22\n'
                'CRT_STEP reject_breakpoint t=0x1p-10 dt=0x1p-19 target=0x1p-21\n')
            result=solver_profile.audit_profile(p,start_s=0,end_s=.002)
            self.assertEqual(result['counts']['reject_lte'],1)
            self.assertEqual(result['counts']['accept'],1)
            self.assertEqual(result['lte_last_instrumented_device'],{'IND:l1':1})
            self.assertEqual(len(result['device_truncation_proposals']),2)
            with self.assertRaises(ValueError):solver_profile.audit_profile(p,start_s=0,end_s=.0001)
            p.write_text('CRT_STEP accept t=nan next_dt=0x1p-22\n')
            with self.assertRaises(ValueError):solver_profile.audit_profile(p,start_s=0,end_s=.002)


@unittest.skipUnless(os.environ.get('MONITOR_RUNTIME'),'Set MONITOR_RUNTIME to a pinned build for native checks')
class NativeRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binary,_=runtime.verify(os.environ['MONITOR_RUNTIME'])

    def solve(self,circuit,*,step=5e-8,stop=4e-5,audit=False,pipe=False):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'run.cir').write_text('Comparator test\n'+circuit+f'''
.model TEST crt_schmitt(low=1.3 high=5.7 edge_s=20n)
.options reltol=1e-5 abstol=1e-12 vntol=1e-9
.save v(in) v(out)
.tran {step} {stop} 0 {step}
.end
''')
            env=os.environ.copy()
            for key in ('CRT_AUDIT_FROM','CRT_AUDIT_TO'):env.pop(key,None)
            if audit:env.update(CRT_AUDIT_FROM='0',CRT_AUDIT_TO=str(stop))
            argv=[str(self.binary),'-n','-b','-r','trace.raw','run.cir']
            kwargs={};chunks=[]
            if pipe:
                read_fd,write_fd=os.pipe()
                def consume():
                    with os.fdopen(read_fd,'rb') as stream:chunks.append(stream.read())
                reader=threading.Thread(target=consume);reader.start()
                argv[-2]=f'/dev/fd/{write_fd}';kwargs['pass_fds']=(write_fd,)
            try:
                result=subprocess.run(argv,cwd=root,env=env,capture_output=True,timeout=30,**kwargs)
            finally:
                if pipe:os.close(write_fd);reader.join(timeout=5)
            if pipe:(root/'trace.raw').write_bytes(chunks[0])
            log=(result.stdout+result.stderr).decode()
            self.assertEqual(result.returncode,0,log)
            self.assertIsNone(re.search(r'error|aborted|timestep too small',log,re.I),log)
            (root/'solver.log').write_text(log)
            report=solver_profile.profile(root/'trace.raw',expected_end_s=stop,log_path=root/'solver.log')
            self.assertEqual(report['completed_endpoint'],not pipe)
            if pipe:
                self.assertEqual(report['declared_rows'],0)
                self.assertAlmostEqual(report['last_sample']['time'],stop,delta=1e-15)
            payload=(root/'trace.raw').read_bytes().split(b'Binary:\n',1)[1]
            rows=list(struct.iter_unpack('=3d',payload))
            detail=solver_profile.audit_profile(root/'solver.log',start_s=0,end_s=stop) if audit else None
            return rows,payload,detail

    def test_hysteresis_and_audit_has_no_effect_on_waveform(self):
        circuit='Vin in 0 PWL(0 0 10u 6 15u 3 20u 6 30u 0 40u 0)\nAcompare in out TEST\n'
        rows,plain,_=self.solve(circuit)
        audited,data,report=self.solve(circuit,audit=True)
        self.assertEqual(data,plain)
        _,piped,_=self.solve(circuit,pipe=True)
        self.assertEqual(piped,plain)
        self.assertEqual(report['counts']['accept'],len(audited))
        self.assertGreater(report['counts']['reject_breakpoint'],0)
        self.assertTrue(all(r[2]>.999 for r in rows if 11e-6<r[0]<25e-6))
        self.assertTrue(all(r[2]<.001 for r in rows if r[0]<9.49e-6 or r[0]>28e-6))

    def test_closed_feedback_oscillator_survives_crossing_retries_and_refinement(self):
        circuit='Ctim in 0 6.4n IC=0\nBcharge 0 in I={.0010671875*(1-v(out))}\nBdischarge in 0 I={.0044*v(out)}\nAcompare in out TEST\n'
        def frequency(step):
            rows,_,audit=self.solve(circuit,step=step,stop=.001,audit=True)
            edges=[a[0]+(3.5-a[1])/(b[1]-a[1])*(b[0]-a[0]) for a,b in zip(rows,rows[1:]) if a[0]>.0002 and a[1]<3.5<=b[1]]
            self.assertGreater(len(edges),20)
            self.assertGreater(audit['counts']['reject_breakpoint'],0)
            return (len(edges)-1)/(edges[-1]-edges[0])
        coarse=frequency(1e-7);fine=frequency(2.5e-8)
        self.assertAlmostEqual(coarse,30500,delta=305)
        self.assertAlmostEqual(coarse,fine,delta=30.5)


@unittest.skipUnless(os.environ.get('MONITOR_RUNTIME'),'Set MONITOR_RUNTIME for controller history checks')
class NativeControllerTests(test_controller.ControllerTests):
    def setUp(self):
        binary,_=runtime.verify(os.environ['MONITOR_RUNTIME'])
        read=Path.read_text;run=lab.run_command
        def model(path,*args,**kwargs):
            text=read(path,*args,**kwargs)
            return controller_history.experimental_model(text) if path==ROOT/'devices/tda1060.cir' else text
        def command(argv,*args,**kwargs):
            if argv[0]=='ngspice':argv=[str(binary),'-n',*argv[1:]]
            return run(argv,*args,**kwargs)
        self.read_patch=patch.object(Path,'read_text',model);self.run_patch=patch.object(lab,'run_command',command)
        self.read_patch.start();self.run_patch.start()
        self.addCleanup(self.read_patch.stop);self.addCleanup(self.run_patch.stop)


if __name__=='__main__':unittest.main()
