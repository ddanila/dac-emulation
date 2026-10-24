import subprocess,tempfile,unittest
from pathlib import Path
HERE=Path(__file__).resolve().parent
CODE=r'''
#include <assert.h>
#include <string.h>
#include "dac_anchor.h"
int main(void) {
 const double up=5e9,down=2.5e9,t0=1e-8;
 RobotronDacRamp initial={0,0,0};
 RobotronDacRamp edge=robotron_dac_trial(&initial,t0,t0,5,up,down);
 assert(robotron_dac_value(&edge,t0,up,down)==0);
 assert(robotron_dac_value(&edge,t0+2e-9,up,down)==5);
 /* Repeated accepted partitions must not re-anchor an unchanged ramp. */
 RobotronDacRamp subdivided=edge;
 for(int i=1;i<87;i++)subdivided=robotron_dac_trial(&subdivided,t0+i*1e-11,t0,5,up,down);
 assert(memcmp(&subdivided,&edge,sizeof edge)==0);
 assert(robotron_dac_value(&subdivided,t0+.87e-9,up,down)==robotron_dac_value(&edge,t0+.87e-9,up,down));
 /* Interrupt at the analytical value, with asymmetric falling slope. */
 double changed=t0+.4e-9;
 RobotronDacRamp falling=robotron_dac_trial(&edge,changed,changed,0,up,down);
 assert(falling.value==robotron_dac_value(&edge,changed,up,down));
 assert(fabs(robotron_dac_value(&falling,changed+.2e-9,up,down)-1.5)<1e-13);
 RobotronDacRamp unknown=robotron_dac_trial(&falling,changed+.2e-9,changed+.2e-9,2.5,up,down);
 assert(fabs(unknown.value-1.5)<1e-13);
 assert(robotron_dac_value(&unknown,changed+2e-9,up,down)==2.5);
 /* Discard a trial beyond a reversal, then retry from accepted state. */
 RobotronDacRamp saved=edge;
 RobotronDacRamp rejected=robotron_dac_trial(&saved,t0+2e-9,changed,0,up,down);
 (void)rejected;
 assert(memcmp(&saved,&edge,sizeof edge)==0);
 RobotronDacRamp retried=robotron_dac_trial(&saved,t0+.5e-9,changed,0,up,down);
 assert(memcmp(&retried,&falling,sizeof falling)==0);
 RobotronDacRamp future=robotron_dac_trial(&edge,t0+.2e-9,changed,0,up,down);
 assert(memcmp(&future,&edge,sizeof edge)==0);
 return 0;
}
'''
class AnchoredRampTests(unittest.TestCase):
 def test_compiled_partition_interruption_and_trial_isolation(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'test.c').write_text(CODE)
   subprocess.run(['cc','-std=c11','-O2','-I'+str(HERE/'engine-patches'),str(p/'test.c'),'-lm','-o',str(p/'test')],check=True)
   subprocess.run([str(p/'test')],check=True)
if __name__=='__main__':unittest.main()
