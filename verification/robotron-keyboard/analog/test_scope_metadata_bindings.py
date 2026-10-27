import copy,json,shutil,tempfile,unittest
from pathlib import Path
from scope_metadata_bindings import HERE,parse,review,validate,reference_parse
from scope_metadata import review as metadata_review
from scope_metadata_records import assess
from retained_evidence import check

ROOT=HERE/'reports/scope-metadata-bindings'

class ScopeMetadataBindingsTests(unittest.TestCase):
    def before(self):
        text=(ROOT/'enabled.stdout').read_text();a=text.index('VSM_BEGIN ');b=text.index('BUNDLE_END',a)
        return parse(text[a:b].splitlines())
    def test_retained_controls(self):
        check(ROOT)
        self.assertEqual(review(ROOT),json.loads((ROOT/'assessment.json').read_text()))
        self.assertEqual(metadata_review(ROOT/'metadata-controls'),json.loads((ROOT/'metadata-controls/assessment.json').read_text()))
        self.assertEqual(assess(ROOT/'metadata-controls/enabled.stdout')['imageCount'],32)
    def test_cross_observer_mismatches_refuse(self):
        base=self.before()
        def missing_object(s):s['reference']['objects']=[x for x in s['reference']['objects'] if x['pointer']!=s['signals']['rows'][0]['pointer']]
        def changed_type(s):
            p=s['signals']['rows'][0]['pointer'];next(x for x in s['reference']['objects'] if x['pointer']==p)['type']=999
        mutations=[lambda s:s['reference'].update(tick=0),
            lambda s:s['reference']['scopes'][0].update(pointer=1),
            lambda s:s['membership']['scopes'][0].update(type=32),
            lambda s:s['signals']['rows'][0].update(scope=1),
            lambda s:s['signals']['rows'][0].update(scopeId=999),
            lambda s:s['signals']['rows'][0].update(pointer=1),missing_object,changed_type,
            lambda s:s['metadata']['scopes'][1]['intern'].append(s['metadata']['scopes'][1]['intern'][0])]
        for i,mutate in enumerate(mutations):
            with self.subTest(mutation=i):
                state=copy.deepcopy(base);mutate(state)
                with self.assertRaises(ValueError):validate(state)
    def test_reference_truncation_and_alias_refuse(self):
        text=(ROOT/'enabled.stdout').read_text();a=text.index('VSMR_BEGIN ');b=text.index('VSC_BEGIN ',a);lines=text[a:b].splitlines()
        for size in range(1,len(lines)):
            with self.subTest(size=size),self.assertRaises(ValueError):reference_parse(lines[:size])
        mutated=list(lines);parts=mutated[2].split();parts[1]=mutated[1].split()[1];mutated[2]=' '.join(parts)
        with self.assertRaises(ValueError):reference_parse(mutated)
    def test_missing_fault_or_changed_continuation_refuses(self):
        for old,new in (('REFUSED intern\n',''),('CONTINUE 5 2','CONTINUE 3 2'),('IMAGE restored1','IMAGE before1')):
            with self.subTest(old=old),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp)/'copy';shutil.copytree(ROOT,out);p=out/'enabled.stdout';p.write_text(p.read_text().replace(old,new,1))
                with self.assertRaises(ValueError):review(out)

if __name__=='__main__':unittest.main()
