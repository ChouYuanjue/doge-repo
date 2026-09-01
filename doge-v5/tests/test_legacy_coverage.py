import json,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class LegacyCoverageTests(unittest.TestCase):
 def setUp(self): self.c=json.loads((ROOT/'legacy_coverage.json').read_text())
 def test_v4_every_plugin_has_home(self):
  actual={p.name for p in (ROOT.parent/'doge-v4').iterdir() if p.is_dir() and not p.name.startswith('.')}
  self.assertEqual(actual,set(self.c['v4']))
 def test_v2_every_rule_has_home(self):
  rules=json.loads((ROOT.parent/'doge-v2'/'v2_epk_config.json').read_text())
  self.assertEqual([x['id'] for x in self.c['v2_rules']],list(range(len(rules))))
  self.assertTrue(all(x['destination'] for x in self.c['v2_rules']))
 def test_v3_documented_domains_have_home(self):
  required={'docs','ask','chat','run','wa','tex','siku','poem','yg','gpt','dream','style','toonify','gen','insult','phil','chem','chart','perc','fru','rua','meme','genshin','amuse','cotool','netool','game','math','px','jeffjoke','gan','yan','se','other'}
  self.assertEqual(required,set(self.c['v3']))
 def test_no_unclassified_destination(self):
  vals=list(self.c['v3'].values())+list(self.c['v4'].values())+[x['destination'] for x in self.c['v2_rules']]
  self.assertFalse([x for x in vals if not x or x.startswith('TODO') or x=='unknown'])
if __name__=='__main__': unittest.main()
