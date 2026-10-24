"""Check actual ngspice irreversible-client registration and duplicate warning."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE=Path(__file__).resolve().parent
HEADER=r'''
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
typedef struct {unsigned irreversible;struct {char *GENname;} gen;} MIFinstance;
typedef struct {struct {int num_hybrids;} counts;struct {MIFinstance **hybrids;} info;} Evt_Ckt_Data_t;
typedef struct {Evt_Ckt_Data_t *evt;} CKTcircuit;
static struct {MIFinstance *instance;struct {int init;} circuit;CKTcircuit *ckt;} g_mif_info;
#define cp_err stderr
#define TREALLOC(type,p,n) ((type*)realloc(p,(n)*sizeof(type)))
'''
MAIN=r'''
int main(void) {
 MIFinstance a={0,{"sole_hdl"}},b={0,{"other_hybrid"}},c={0,{"third_hybrid"}},d={0,{"second_hdl"}};
 Evt_Ckt_Data_t evt={0};CKTcircuit ckt={&evt};
 evt.counts.num_hybrids=3;evt.info.hybrids=malloc(3*sizeof(MIFinstance*));
 evt.info.hybrids[0]=&a;evt.info.hybrids[1]=&b;evt.info.hybrids[2]=&c;
 g_mif_info.ckt=&ckt;g_mif_info.circuit.init=1;g_mif_info.instance=&a;
 cm_irreversible(1);
 assert(evt.info.hybrids[0]==&b&&evt.info.hybrids[1]==&c&&evt.info.hybrids[2]==&a);
 /* Registering another hybrid at a higher priority leaves priority 1 last. */
 g_mif_info.instance=&b;cm_irreversible(2);
 assert(evt.info.hybrids[0]==&c&&evt.info.hybrids[1]==&b&&evt.info.hybrids[2]==&a);
 /* Another fully irreversible client is permitted but explicitly warned. */
 g_mif_info.instance=&d;cm_irreversible(1);
 assert(evt.counts.num_hybrids==4);
 /* Do not dispatch duplicate-priority clients: registration only warns. */
 free(evt.info.hybrids);
 puts("priority-1 client runs last; duplicate priority warns but is not rejected");
 return 0;
}
'''


class RegistrationTests(unittest.TestCase):
    def test_real_registration_orders_sole_client_and_warns_on_duplicate(self):
        source=(HERE/'fixtures/ngspice-47/cm.c').read_text()
        self.assertEqual(hashlib.sha256(source.encode()).hexdigest(),
                         'b62c7b7d0051c5b73bdb520f302f52b3db2d6e392c1cd45f8dc62f631e247537')
        function=source[source.index('static void duplicate('):source.index('/* Get the name of a circuit node')]
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'test.c').write_text(HEADER+function+MAIN)
            subprocess.run(['cc','-std=c11','-O2',str(root/'test.c'),'-o',str(root/'test')],check=True)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True,check=True)
            self.assertIn('Warning: Duplicate value 1 in cm_irreversible()',result.stderr)
            print(result.stdout.strip())


if __name__=='__main__':unittest.main()
