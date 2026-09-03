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
 def test_relaxed_translation_fills_common_gaps_without_polluting_exact_layer(self):
  exact,segs=self.d.translate_chinese('隐藏的城市')
  self.assertIn('□',exact)
  relaxed,notes,coverage=self.d.relaxed_chinese(segs)
  self.assertNotIn('□',relaxed)
  self.assertEqual(coverage,1.0)
  self.assertTrue(any('的→〔省略虚词〕' in x for x in notes))
  self.assertEqual(self.d.translate_chinese('隐藏的城市')[0],exact)
 def test_relaxed_content_neighbor_avoids_obvious_person_name_for_machine(self):
  exact,segs=self.d.translate_chinese('机器改变身体')
  self.assertIn('□',exact)
  relaxed,notes,coverage=self.d.relaxed_chinese(segs)
  self.assertNotIn('□',relaxed)
  self.assertEqual(coverage,1.0)
  self.assertTrue(any(x.startswith('机≈') for x in notes))
  self.assertFalse(any('陆机' in x for x in notes))

 def test_word_level_relaxed_options_use_dictionary_only_and_drop_function_word(self):
  rows=self.d.relaxed_word_options('机器改变身体',12)
  self.assertEqual([r['source'] for r in rows],['机器','改变','身体'])
  self.assertEqual(rows[2]['kind'],'exact')
  for row in rows:
   for entry in row['options']:
    self.assertIn(entry.key,self.d.forward)
  rows2=self.d.relaxed_word_options('隐藏的城市',12)
  drop=next(r for r in rows2 if r['source']=='的')
  self.assertEqual(drop['kind'],'drop')
 def test_word_choice_can_select_nondefault_semantic_candidate_without_generating_glyphs(self):
  rows=self.d.relaxed_word_options('机器改变身体',12)
  machine=rows[0]
  idx=next(i for i,e in enumerate(machine['options']) if '器具' in e.cn)
  expected=machine['options'][idx].key
  out,notes,cov=self.d.render_word_choices(rows,{0:idx})
  self.assertTrue(out.startswith(expected))
  self.assertEqual(cov,1.0)
  self.assertTrue(any('机器≈'+expected in note for note in notes))
  self.assertTrue(all(ch=='□' or ch.isspace() or ch in '，。！？；：、,.!?;:' or ch in ''.join(self.d.forward.keys()) for ch in out))
 def test_word_level_relaxed_does_not_change_exact_translator_contract(self):
  exact_before,_=self.d.translate_chinese('隐藏的城市')
  self.d.render_word_choices(self.d.relaxed_word_options('隐藏的城市',12),{})
  exact_after,_=self.d.translate_chinese('隐藏的城市')
  self.assertEqual(exact_before,exact_after)

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
