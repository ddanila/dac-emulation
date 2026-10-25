import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from raw_stream_review import compare_streams
from raw_pair_review import compare_raw
from test_raw_pair_review import write


class StreamReviewTests(unittest.TestCase):
    def test_unknown_header_counts_and_different_grids_match_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            a,b=Path(tmp)/'a',Path(tmp)/'b'
            write(a,[(0,0),(.5,2),(1,0)]);write(b,[(0,0),(.25,1),(.5,2),(.75,1.1),(1,0)])
            expected=compare_raw(a,b,[3,5],1)
            with a.open('rb') as x,b.open('rb') as y:
                result=compare_streams(x,y,1,lambda:[3,5])
            self.assertEqual(result['comparison'],expected)
            for path,receipt in zip((a,b),result['streams']):
                self.assertEqual(receipt['sha256'],hashlib.sha256(path.read_bytes()).hexdigest())

    def test_failed_producer_count_truncation_and_trailing_row_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a';write(a,[(0,0),(1,1)]);data=a.read_bytes()
            for damaged,counts in [(data,[2,3]),(data[:-1],[2,2]),(data+b'bad',[2,2])]:
                with self.subTest(counts=counts),self.assertRaises(ValueError):
                    compare_streams(io.BytesIO(data),io.BytesIO(damaged),1,lambda:counts,exact=True)
            def failed():raise ValueError('Producer failed after raw EOF')
            with self.assertRaisesRegex(ValueError,'Producer failed'):
                compare_streams(io.BytesIO(data),io.BytesIO(data),1,failed,exact=True)

    def test_completion_checked_only_after_both_streams_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            a=Path(tmp)/'a';write(a,[(0,0),(1,1)]);data=a.read_bytes()
            x,y=io.BytesIO(data),io.BytesIO(data)
            def counts():
                self.assertEqual(x.tell(),len(data));self.assertEqual(y.tell(),len(data));return [2,2]
            self.assertTrue(compare_streams(x,y,1,counts,exact=True)['completed'])

if __name__=='__main__':unittest.main()
