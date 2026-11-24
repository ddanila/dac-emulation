"""Cheap checks for media preparation and comparison logic; no historical media."""
import tempfile
import unittest
from pathlib import Path
from prepare import physical,prepare
from run import schedule

class ToolsTest(unittest.TestCase):
    def test_sector_mapping(self):
        offsets={physical(i*512) for i in range(1600)}
        self.assertEqual(offsets,set(range(0,819200,512)))
        self.assertEqual(physical(2*5120),2*10240)
        self.assertEqual(physical(80*5120),5120)

    def test_add_file_preserves_allocated_data_and_source(self):
        raw=bytearray([0xe5])*819200
        entry=bytearray(32);entry[1:12]=b'EXIST   COM';entry[15]=32;entry[16]=1
        for i,v in enumerate(entry):raw[physical(10240+i)]=v
        for i in range(4096):raw[physical(10240+4096+i)]=i%251
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'source.juk';out=Path(d)/'copy.juk';source.write_bytes(raw)
            info=prepare(source,out);self.assertEqual(info['block'],2)
            self.assertEqual(source.read_bytes(),raw)
            result=out.read_bytes()
            for i in range(4096):self.assertEqual(result[physical(10240+4096+i)],i%251)
            with self.assertRaises(ValueError):prepare(out,Path(d)/'duplicate.juk')
            with self.assertRaises(ValueError):prepare(source,source)
            self.assertEqual(source.read_bytes(),raw)

    def test_schedule_release_and_scaling(self):
        for context in ['ekdos','monitor','diagnostic']:
            for scale in [0.5,1,2]:
                rows,end,start=schedule(context,'\x1b:',scale)
                self.assertEqual(rows,sorted(rows))
                self.assertLess(rows[-1][0],end)
                self.assertGreater(start,rows[1][0])
                for press,release in zip(rows[::2],rows[1::2]):
                    self.assertEqual(press[2],1)
                    self.assertEqual(release[1:],(0,0))
                    self.assertEqual(release[0]-press[0],round(120*scale))

if __name__=='__main__':unittest.main()
