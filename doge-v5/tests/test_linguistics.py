from __future__ import annotations
import importlib.util,json,sys,tempfile,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
LING=ROOT/'plugins'/'doge_linguistics'
if str(LING) not in sys.path: sys.path.insert(0,str(LING))

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
 @classmethod
 def setUpClass(cls): cls.root=LING/'assets'/'Rlyehian-Cthuvian-Translator'

 def test_pinned_checkout_adapter(self):
  a=ling.CthuvianAdapter(self.root)
  r=a.translate('I do not know everything.','low')
  self.assertTrue(r['roundtrip_ok'])
  self.assertIn('kadishtu',r['cthuvian'])

 def test_full_upstream_static_registry_is_loaded(self):
  a=ling.CthuvianAdapter(self.root)
  self.assertGreaterEqual(len(a.registry.all_entries()),4000)
  self.assertIsNotNone(a.lookup('computer'))

 def test_low_register_never_mutates_learned_registry(self):
  with tempfile.TemporaryDirectory() as td:
   learned=Path(td)/'learned-registry.json'
   a=ling.CthuvianAdapter(self.root,learned)
   before_count=a.learned_count(); before_bytes=a.learned_bytes()
   for _ in range(3):
    r=a.translate('I know quantumwidget','low')
    self.assertEqual(r['provenance'],'hybrid')
    self.assertIn('quantumwidget',a.sealed_sources(r))
   self.assertEqual(a.learned_count(),before_count)
   self.assertEqual(a.learned_bytes(),before_bytes)
   self.assertFalse(learned.exists())

 def test_accept_persists_reverse_reloads_and_rejects_collision(self):
  with tempfile.TemporaryDirectory() as td:
   learned=Path(td)/'learned-registry.json'
   a=ling.CthuvianAdapter(self.root,learned)
   proposal={
    'source_term':'quantumwidget','concept_type':'object','selected_roots':[],
    'literal_gloss':'quantumwidget','needs_new_root':True,'coined_surface':"qth'vra",
   }
   accepted=a.accept_proposal('quantumwidget',proposal,'deepseek/test')
   self.assertTrue(accepted['created'])
   self.assertEqual(a.learned_count(),1)
   payload=json.loads(learned.read_text(encoding='utf-8'))
   self.assertIn('accepted_at',payload['entries']['quantumwidget'])
   self.assertEqual(payload['entries']['quantumwidget']['model_profile'],'deepseek/test')

   high=a.translate('I know quantumwidget','high')
   self.assertEqual(high['provenance'],'lexicon')
   self.assertFalse(a.sealed_sources(high))
   self.assertIn('quantumwidget',a.gloss(accepted['rc'])['best_gloss'])

   reloaded=ling.CthuvianAdapter(self.root,learned)
   self.assertEqual(reloaded.lookup('quantumwidget').rc,accepted['rc'])
   self.assertEqual(reloaded.translate('I know quantumwidget','high')['cthuvian'],high['cthuvian'])
   same=reloaded.accept_proposal('quantumwidget',proposal,'deepseek/test')
   self.assertFalse(same['created'])

   collision=dict(proposal,source_term='neutrinoartifact',literal_gloss='neutrinoartifact')
   with self.assertRaisesRegex(ValueError,'collision'):
    reloaded.accept_proposal('neutrinoartifact',collision,'deepseek/test')

 def test_learned_coined_surface_must_be_single_reversible_token(self):
  with tempfile.TemporaryDirectory() as td:
   a=ling.CthuvianAdapter(self.root,Path(td)/'learned-registry.json')
   proposal={
    'source_term':'quantumwidget','concept_type':'object','selected_roots':[],
    'literal_gloss':'quantumwidget','needs_new_root':True,'coined_surface':"qth vra",
   }
   self.assertTrue(a.validate_proposal(proposal)['ok'])  # upstream parity
   with self.assertRaisesRegex(ValueError,'single reversible token'):
    a.accept_proposal('quantumwidget',proposal,'deepseek/test')

if __name__=='__main__': unittest.main()
