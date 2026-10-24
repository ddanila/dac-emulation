import unittest
from startup_passive_review import validate_controls, CASES

class StampingControls(unittest.TestCase):
 def receipts(self):
  return {name:{'conservativeCap':name!='precision','passiveAssembly':name in ('passive','extended'),
      'stopNs':1006000 if name=='extended' else 2000,'mpfrStartNs':0,'toleranceScale':.1,
      'toleranceComponents':['reltol'],'deckSha256':'long' if name=='extended' else 'short',
      'runtime':'same','sourceDeckSha256':'same','samplingGridSha256':'same'} for name in CASES}
 def test_only_declared_changes_are_allowed(self):
  validate_controls(self.receipts())
  for field,value in [('runtime','changed'),('sourceDeckSha256','changed'),('samplingGridSha256','changed'),
      ('toleranceComponents',['abstol']),('mpfrStartNs',1000),('conservativeCap',False),('passiveAssembly',False),('stopNs',100)]:
   receipts=self.receipts();receipts['extended'][field]=value
   with self.assertRaises(ValueError):validate_controls(receipts)
 def test_short_decks_and_controls_must_match(self):
  receipts=self.receipts();receipts['capacitor']['deckSha256']='other'
  with self.assertRaises(ValueError):validate_controls(receipts)
  receipts=self.receipts();del receipts['precision']
  with self.assertRaises(ValueError):validate_controls(receipts)

if __name__=='__main__':unittest.main()
