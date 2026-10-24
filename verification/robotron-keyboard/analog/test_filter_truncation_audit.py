import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

class FilterTruncationAuditTests(unittest.TestCase):
    def test_logging_preserves_actual_error_function_and_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, subdir in [('cktterr.c', 'analysis'), ('captrunc.c', 'devices/cap'), ('indtrunc.c', 'devices/ind'), ('bjttrunc.c', 'devices/bjt')]:
                target = root / 'src/spicelib' / subdir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(HERE / 'fixtures/filter-truncation' / name, target)
            subprocess.run(['patch', '-d', str(root), '-p1', '-i', str(HERE / 'engine-patches/ngspice-47-filter-truncation-audit.patch')], check=True, capture_output=True)
            include = root / 'ngspice'; include.mkdir()
            (include / 'ngspice.h').write_text('#include <stdio.h>\n#include <stdlib.h>\n#include <math.h>\n#define MAX(a,b) ((a)>(b)?(a):(b))\n#define MIN(a,b) ((a)<(b)?(a):(b))\n')
            (include / 'cktdefs.h').write_text('''
#define GEAR 1
#define TRAPEZOIDAL 2
struct stats {int STATnumIter;};
typedef struct {double CKTtime,CKTdelta,CKTdeltaOld[8],CKTabstol,CKTreltol,CKTchgtol,CKTtrtol;
int CKTorder,CKTintegrateMethod; double *CKTstate0,*CKTstate1,*CKTstates[8]; struct stats *CKTstat;} CKTcircuit;
''')
            (root / 'test.c').write_text('''
#include "src/spicelib/analysis/cktterr.c"
int main(void) {
 CKTcircuit c={0}; double states[8][2]; struct stats stat={0};
 c.CKTstat=&stat;c.CKTabstol=1e-15;c.CKTreltol=1e-8;c.CKTchgtol=1e-14;c.CKTtrtol=7;c.CKTdelta=1e-10;
 for(int j=0;j<8;j++){c.CKTdeltaOld[j]=1e-10*(1+j*.1);c.CKTstates[j]=states[j];states[j][0]=1e-12*(1+j*.12+j*j*.003);states[j][1]=.001+j*.0001;}
 c.CKTstate0=states[0];c.CKTstate1=states[1];
 double times[]={137.9e-6,138e-6,138.25e-6,138.5e-6,138.6e-6};
 for(int method=1;method<=2;method++)for(int order=1;order<=2;order++)for(int i=0;i<5;i++){
 c.CKTintegrateMethod=method;c.CKTorder=order;c.CKTtime=times[i];double step=1e-6;
 CKTterr(0,&c,&step);printf("%a\\n",step);
 step=1e-30;CKTterr(0,&c,&step);printf("%a\\n",step);
 }
 return 0;
}
''')
            subprocess.run(['cc', '-std=c11', '-O2', '-I'+str(root), str(root/'test.c'), '-lm', '-o', str(root/'test')], check=True)
            env = {k:v for k,v in os.environ.items() if not k.startswith('ROBOTRON_')}
            off = subprocess.run([str(root/'test')], env=env, text=True, capture_output=True, check=True)
            on = subprocess.run([str(root/'test')], env={**env,'ROBOTRON_FILTER_TRUNC_AUDIT':'1'}, text=True, capture_output=True, check=True)
            self.assertEqual(off.stdout, on.stdout)
            self.assertEqual(off.stderr, '')
            lines = on.stderr.splitlines()
            self.assertEqual(len(lines), 12)
            for line in lines:
                values = dict(item.split('=',1) for item in line.split()[2:])
                self.assertTrue(138e-6 <= float.fromhex(values['time']) <= 138.5e-6)
                self.assertIn('chargetol', values)
                self.assertIn('q3', values)

    def test_bjt_state_identity_and_unchanged_calls(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for name,subdir in [('cktterr.c','analysis'),('captrunc.c','devices/cap'),('indtrunc.c','devices/ind'),('bjttrunc.c','devices/bjt')]:
                target=root/'src/spicelib'/subdir/name;target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(HERE/'fixtures/filter-truncation'/name,target)
            subprocess.run(['patch','-d',str(root),'-p1','-i',str(HERE/'engine-patches/ngspice-47-filter-truncation-audit.patch')],check=True,capture_output=True)
            inc=root/'ngspice';inc.mkdir()
            (inc/'ngspice.h').write_text('#include <stdio.h>\n#include <stdlib.h>\ntypedef void GENmodel;\n')
            (inc/'cktdefs.h').write_text('typedef struct {double CKTtime;} CKTcircuit;\nvoid CKTterr(int,CKTcircuit*,double*);\n')
            (inc/'sperror.h').write_text('#define OK 0\n');(inc/'suffix.h').write_text('')
            (root/'src/spicelib/devices/bjt/bjtdefs.h').write_text("""
typedef struct {char *BJTname;int BJTqbe,BJTqbc,BJTqsub,BJTqbcx;} BJTinstance;
typedef struct {int BJTintCollResistGiven;BJTinstance *instance;} BJTmodel;
#define BJTnextModel(m) NULL
#define BJTinstances(m) ((m)->instance)
#define BJTnextInstance(i) NULL
""")
            (root/'test.c').write_text("""
#include "src/spicelib/devices/bjt/bjttrunc.c"
static int reduce;
void CKTterr(int state,CKTcircuit *c,double *step){printf("%d %a\\n",state,*step);if(reduce)*step*=.5;}
int main(void){BJTinstance i={"q_driver",10,12,14,16};BJTmodel m={0,&i};CKTcircuit c={0};
 double times[]={137.9e-6,138e-6,138.25e-6,138.5e-6,138.6e-6};
 for(int given=0;given<2;given++)for(reduce=0;reduce<2;reduce++)for(int t=0;t<5;t++){
 m.BJTintCollResistGiven=given;c.CKTtime=times[t];double step=1;BJTtrunc(&m,&c,&step);printf("%a\\n",step);}
 return 0;}
""")
            subprocess.run(['cc','-std=c11','-O2','-I'+str(root),str(root/'test.c'),'-o',str(root/'test')],check=True)
            env={k:v for k,v in os.environ.items() if not k.startswith('ROBOTRON_')}
            off=subprocess.run([str(root/'test')],env=env,text=True,capture_output=True,check=True)
            on=subprocess.run([str(root/'test')],env={**env,'ROBOTRON_FILTER_TRUNC_AUDIT':'1'},text=True,capture_output=True,check=True)
            self.assertEqual(off.stdout,on.stdout);self.assertEqual(off.stderr,'')
            lines=on.stderr.splitlines();self.assertEqual(len(lines),21)
            counts={}
            for line in lines:
                record=dict(item.split('=',1) for item in line.split()[2:])
                self.assertEqual(record['name'],'q_driver')
                self.assertTrue(138e-6<=float.fromhex(record['time'])<=138.5e-6)
                self.assertLess(float.fromhex(record['proposed']),float.fromhex(record['before']))
                state=int(record['state']);counts[state]=counts.get(state,0)+1
            self.assertEqual(counts,{10:6,12:6,14:6,16:3})

if __name__ == '__main__':
    unittest.main()
