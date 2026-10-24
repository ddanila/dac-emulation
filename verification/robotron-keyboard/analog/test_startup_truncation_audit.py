import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent

class TruncationAuditTests(unittest.TestCase):
    def test_logging_preserves_actual_error_function_and_window(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, subdir in [('cktterr.c', 'analysis'), ('captrunc.c', 'devices/cap'), ('indtrunc.c', 'devices/ind')]:
                target = root / 'src/spicelib' / subdir / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(HERE / 'fixtures/startup-truncation' / name, target)
            subprocess.run(['patch', '-d', str(root), '-p1', '-i', str(HERE / 'engine-patches/ngspice-47-startup-truncation-audit.patch')], check=True, capture_output=True)
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
 double times[]={.74e-6,.75e-6,.9e-6,1.05e-6,1.06e-6};
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
            on = subprocess.run([str(root/'test')], env={**env,'ROBOTRON_STARTUP_TRUNC_AUDIT':'1'}, text=True, capture_output=True, check=True)
            self.assertEqual(off.stdout, on.stdout)
            self.assertEqual(off.stderr, '')
            lines = on.stderr.splitlines()
            self.assertEqual(len(lines), 12)
            for line in lines:
                values = dict(item.split('=',1) for item in line.split()[2:])
                self.assertTrue(.75e-6 <= float.fromhex(values['time']) <= 1.05e-6)
                self.assertIn('chargetol', values)
                self.assertIn('q3', values)

if __name__ == '__main__':
    unittest.main()
