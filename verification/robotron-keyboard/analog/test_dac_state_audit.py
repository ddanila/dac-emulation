import os,subprocess,tempfile,unittest
from pathlib import Path
from diagnostic_halt import add_halt
HERE=Path(__file__).resolve().parent

class DacStateAuditTests(unittest.TestCase):
 def test_halt_preserves_transient_and_stimulus(self):
  deck='fixture\nV1 v 0 5\n.tran 25n 1006000n\n.control\nrun\n.endc\n'
  result=add_halt(deck,12,1006000)
  self.assertEqual(result.replace('stop when time > 12n\n',''),deck)
  for time in (0,1006000,float('nan')):
   with self.assertRaises(ValueError):add_halt(deck,time,1006000)
 def test_compiled_logging_preserves_evaluator(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);p=root/'src/xspice/icm/digital/dac_bridge/cfunc.mod';p.parent.mkdir(parents=True)
   p.write_text((HERE/'fixtures/ngspice-47/dac_bridge.mod').read_text())
   for name in ('dac-ramp-breakpoint.patch','dac-state-audit.patch'):
    subprocess.run(['patch','-d',str(root),'-p1','-i',str(HERE/'engine-patches'/name)],check=True,capture_output=True)
   code=p.read_text();start=code.index('        /* Multiple single-bit conversions. */');end=code.index('\n        break;\n\n    default:',start)
   stub='#include <stdarg.h>\nstatic const char *cm_get_node_name(const char *p,int i){return "wr_high";}\nstatic void cm_message_printf(const char *f,...){va_list a;va_start(a,f);vfprintf(stderr,f,a);fputc(10,stderr);va_end(a);}\n'
   harness=(HERE/'fixtures/dac_ramp_harness.c').read_text().replace('static double evaluate(',stub+'static double evaluate(').replace('/* SINGLE_BIT_EVALUATOR */',code[start:end]).replace('.001005012','1e-8')
   (root/'test.c').write_text(harness);subprocess.run(['cc','-std=gnu11','-O2',str(root/'test.c'),'-lm','-o',str(root/'test')],check=True)
   env={k:v for k,v in os.environ.items() if k!='ROBOTRON_DAC_STATE_AUDIT'}
   off=subprocess.run([str(root/'test'),'1'],env=env,text=True,capture_output=True,check=True)
   on=subprocess.run([str(root/'test'),'1'],env=dict(env,ROBOTRON_DAC_STATE_AUDIT='1'),text=True,capture_output=True,check=True)
   self.assertEqual(off.stdout,on.stdout);self.assertEqual(off.stderr,'');self.assertIn('DAC_STATE time=',on.stderr)

if __name__=='__main__':unittest.main()
