from __future__ import annotations
import importlib.util,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LING=ROOT/'plugins'/'doge_linguistics'

def load(name,file):
 spec=importlib.util.spec_from_file_location(name,LING/file); mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod); return mod
ling=load('doge_test_linguistics','linguistics.py')
rrpl=load('doge_test_rrpl','rrpl_py.py')

class TangutTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls): cls.d=ling.TangutDictionary(LING/'assets'/'tangut-dictionary.json')
 def test_exact_multichar_gloss_beats_character_split(self):
  text,segs=self.d.translate_chinese('中国')
  self.assertEqual(text,'𘇂𗂧')
  self.assertEqual(len(segs),1)
  self.assertEqual(segs[0].source,'中国')
 def test_unknown_never_becomes_fuzzy_fake_translation(self):
  text,segs=self.d.translate_chinese('𠮷𠮷𠮷')
  self.assertIn('□',text)
 def test_tangut_longest_word_match(self):
  units,gloss=self.d.literal_gloss('𘛛𗅛')
  self.assertEqual(len(units),1)
  self.assertEqual(gloss,'太阳')
 def test_ranked_lookup_prefers_exact_gloss(self):
  rows=self.d.search_chinese('国家',4)
  self.assertTrue(rows)
  self.assertTrue(all(x.cn=='国家' for x,_ in rows))

class RrplTests(unittest.TestCase):
 def test_reference_expansion_is_pure_rrpl(self):
  refs=rrpl.load_reference_dict(LING/'assets'/'rrpl.json')
  expanded=rrpl.expand_references('廿|468|由|(八)',refs)
  self.assertTrue(expanded)
  self.assertTrue(set(expanded)<=set('012345678|-()'))
 def test_parser_geometry(self):
  tree=rrpl.parse('(48|37)-(25678|27)-(37|15)')
  lines=rrpl.to_lines(rrpl.to_rects(tree))
  self.assertGreater(len(lines),5)

class CthuvianTests(unittest.TestCase):
 def test_pinned_checkout_adapter(self):
  a=ling.CthuvianAdapter(LING/'assets'/'Rlyehian-Cthuvian-Translator')
  r=a.translate('I do not know everything.','low')
  self.assertTrue(r['roundtrip_ok'])
  self.assertIn('kadishtu',r['cthuvian'])

if __name__=='__main__': unittest.main()
