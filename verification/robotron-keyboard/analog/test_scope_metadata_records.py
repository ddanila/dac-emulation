import json
from pathlib import Path
import tempfile
import unittest
from scope_metadata_records import parse,images,assess
from retained_evidence import check

HERE=Path(__file__).resolve().parent
SOURCE=HERE/'reports/scope-metadata/enabled.stdout'

class ScopeMetadataRecordTests(unittest.TestCase):
    def setUp(self):
        text=SOURCE.read_text();start=text.index('VSM_BEGIN ');end=text.index('\nIMAGE units1')
        self.image=text[start:end].splitlines()
    def test_retained_semantic_review(self):
        root=HERE/'reports/scope-metadata-records';check(root)
        self.assertEqual(assess(SOURCE),json.loads((root/'assessment.json').read_text()))
        self.assertEqual(len(images(SOURCE)),32)
    def test_malformed_or_truncated_records_refuse(self):
        text='\n'.join(self.image)
        substitutions=[('VSM_BEGIN 1','VSM_BEGIN 2'),('VSM_BEGIN 1 1000','VSM_BEGIN 1 -1'),
            ('VSM_SCOPE 2 0','VSM_SCOPE 1 0'),('VSM_SCOPE 2 0','VSM_SCOPE 2 999'),
            ('VSM_SCOPE 2 0 32','VSM_SCOPE 2 0 999'),('VSM_SCOPE 2 0 32','VSM_SCOPE 2 0 20'),
            ('VSM_NAME 5 7465737400','VSM_NAME 6 7465737400'),('7465737400','74657374zz'),
            ('VSM_TIME 0 0 0','VSM_TIME 999 0 0'),('VSM_FUNCTION 5 8 3','VSM_FUNCTION 5 8 4'),
            ('VSM_INTERN 3','VSM_INTERN 999999999999'),('VSM_OBJECT 2 32','VSM_OBJECT 1 32'),
            ('VSM_END 4','VSM_END 3'),('VSM_BEGIN 1','VSM_BEGIN  1'),
            (' 0 -9 -12',' 0 -129 -12'),('VSM_SCOPE 2 0 32 3','VSM_SCOPE 2 0 32 4294967296')]
        for old,new in substitutions:
            with self.subTest(old=old,new=new):
                self.assertIn(old,text)
                with self.assertRaises(ValueError):parse(text.replace(old,new,1).splitlines())
        for size in range(len(self.image)):
            with self.subTest(prefix=size),self.assertRaises(ValueError):parse(self.image[:size])
        with self.assertRaises(ValueError):parse(self.image+['VSM_END 4'])
    def test_byte_content_and_intern_order_remain_lossless(self):
        parsed=images(SOURCE)
        self.assertNotEqual(parsed['before1'],parsed['order1'])
        self.assertNotEqual(parsed['before1'],parsed['omit1'])
        lines=[l.replace('7465737400','74657374ff') for l in self.image]
        self.assertEqual(parse(lines)['scopes'][1]['nameBytes'],'74657374ff')
    def test_semantic_review_refuses_unrelated_field_change(self):
        text=SOURCE.read_text();start=text.index('IMAGE units1');end=text.index('CHANGED units',start)
        section=text[start:end].replace(' 0 -8 -12',' 1 -8 -12')
        self.assertNotEqual(section,text[start:end])
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'changed.stdout';path.write_text(text[:start]+section+text[end:])
            with self.assertRaises(ValueError):assess(path)
    def test_image_boundaries_refuse(self):
        text=SOURCE.read_text()
        for changed in (text.replace('IMAGE restored1','IMAGE before1'),text+'\nIMAGE truncated\n', 'VSM_END 1\n'+text):
            with tempfile.TemporaryDirectory() as tmp:
                path=Path(tmp)/'changed.stdout';path.write_text(changed)
                with self.assertRaises(ValueError):images(path)

if __name__=='__main__':unittest.main()
