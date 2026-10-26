#!/usr/bin/env python3
import copy
import json
from pathlib import Path
import unittest
from postreset_tick_capture import experiment,SOURCES
from postreset_tick_review import validate
from ttl7406_probe import sha
HERE=Path(__file__).resolve().parent


class PostresetTick(unittest.TestCase):
    def setUp(self):
        self.root=HERE/'reports/postreset-adc/25'
        self.base=json.loads((self.root/'run.json').read_text())
        self.deck=(self.root/'io.cir').read_text()
        self.old=next(d['path'] for d in self.base['externalDependencies'] if Path(d['path']).name=='ivlng.vpi')

    def test_experimental_boundaries(self):
        for mode,step in [('off',25),('on',25),('on',12.5),('on',6.25),('retry',25)]:
            deck,env=experiment(self.deck,self.base['environment'],self.old,'/candidate/ivlng.vpi',mode,step)
            self.assertIn('1000000n 0 1000001n 5',deck)
            self.assertIn(f'.tran {step:g}n 1.16e+06n',deck)
            self.assertEqual(env['ROBOTRON_ADC_CROSSINGS'],'1')
            self.assertEqual(env.get('ROBOTRON_ABSOLUTE_TICKS'),None if mode=='off' else '1')
            self.assertEqual(env.get('ROBOTRON_NEWTON_REJECT_START'),'0.0011' if mode=='retry' else None)
        for mode,step in [('off',12.5),('retry',6.25),('on',5),('unknown',25)]:
            with self.assertRaises(ValueError):experiment(self.deck,self.base['environment'],self.old,'/new',mode,step)
        for deck,env,old,new in [
            (self.deck.replace('1.16e+06n','20000n'),self.base['environment'],self.old,'/new'),
            (self.deck,dict(self.base['environment'],ROBOTRON_ADC_CROSSINGS='0'),self.old,'/new'),
            (self.deck,dict(self.base['environment'],ROBOTRON_FORCE_NEWTON_REJECT='1'),self.old,'/new'),
            (self.deck,self.base['environment'],self.old,self.old)]:
            with self.assertRaises(ValueError):experiment(deck,env,old,new,'on',25)

    def test_receipt_rejections(self):
        r=copy.deepcopy(self.base)
        r.update(mode='on',stepNs=25,endSeconds=.00116,baselineReceiptSha256='base',candidateBuildSha256='build',boundedAssessmentSha256='bounded',runtimeEnvironment={'SPICE_SCRIPTS':str(Path(self.base['runtime']['spinit']['path']).parent)},sources={n:sha(HERE/n) for n in SOURCES})
        validate(r,self.base,'on',25,'base','build','bounded')
        for key,value in [('completed',False),('exitCode',2),('endSeconds',20e-6),('stepNs',12.5),('mode','off'),('candidateBuildSha256','wrong'),('boundedAssessmentSha256','wrong'),('sources',{}),('runtimeEnvironment',{})]:
            bad=copy.deepcopy(r);bad[key]=value
            with self.assertRaises(ValueError):validate(bad,self.base,'on',25,'base','build','bounded')
        bad=copy.deepcopy(r);bad['log']['bytes']=bad['limits']['logicalLogBytes']+1
        with self.assertRaises(ValueError):validate(bad,self.base,'on',25,'base','build','bounded')


if __name__=='__main__':unittest.main()
