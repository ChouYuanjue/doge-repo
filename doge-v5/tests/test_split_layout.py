from __future__ import annotations

import ast,json,unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PLUGINS=ROOT/'plugins'
MANIFEST=json.loads((ROOT/'plugin_manifest.json').read_text(encoding='utf-8'))
DEFAULT={x['name'] for x in MANIFEST['plugins'] if x.get('default')}
LEGACY={x['name'] for x in MANIFEST['plugins'] if x.get('status')=='legacy'}


def commands_for(names:set[str]):
 out=set()
 for name in names:
  p=PLUGINS/name/'main.py'
  if not p.exists(): continue
  tree=ast.parse(p.read_text(encoding='utf-8'),filename=str(p))
  for node in ast.walk(tree):
   if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)): continue
   for deco in node.decorator_list:
    if not isinstance(deco,ast.Call) or not isinstance(deco.func,ast.Attribute) or deco.func.attr!='command': continue
    if any(k.arg=='alias' for k in deco.keywords): raise AssertionError(f'AstrBot alias leaked: {p}:{node.lineno}')
    if deco.args and isinstance(deco.args[0],ast.Constant): out.add(str(deco.args[0].value))
 return out

class SplitLayoutTests(unittest.TestCase):
 def test_manifest_plugins_exist(self):
  for name in DEFAULT|LEGACY:
   self.assertTrue((PLUGINS/name/'main.py').exists(),name)
  self.assertTrue((PLUGINS/'doge_shared'/'__init__.py').exists())
  self.assertFalse((PLUGINS/'doge_shared'/'main.py').exists())
  self.assertFalse((PLUGINS/'doge_media'/'main.py').exists()) # planned, not fake-ready

 def test_default_command_surface_is_clean(self):
  expected={'ver','math','util','paper','bio','chem','mat','astro','trial','lab','tex','typst','md','snippet','game','fuse','arena','lang','run','lookup','diagram','ai','cs','eng'}
  self.assertEqual(commands_for(DEFAULT),expected)

 def test_no_command_aliases_in_formal_plugins(self):
  commands_for(DEFAULT) # helper asserts aliases are absent

 def test_historical_commands_do_not_leak_into_default(self):
  retired={'gpt','yg','gan','dream','style','toonify','gen','siku','perc','phil','poem','insult','fru','rua','jeffjoke','px','yan','se','genshin','honkai','pack','doubao','lcha','ltran','lsd','lflux','lcon','limg','amuse','netool','chart','api','emojimix','meme','mirage','music','lyrics','vv','trace','st','mc','law','anime','say','arknights'}
  self.assertTrue(retired.isdisjoint(commands_for(DEFAULT)))
  self.assertTrue(retired.issubset(commands_for(LEGACY)))

 def test_collapsed_old_aliases_are_not_registered(self):
  removed={'doge','encode','decode','cotool','nasa','bing','circuit','control','crystal','chart','signal','shock','wp','sci','latex','utex','typ','tym','yau'}
  self.assertTrue(removed.isdisjoint(commands_for(DEFAULT)))

 def test_default_profile_is_granular(self):
  self.assertGreaterEqual(len(DEFAULT),18)
  for too_broad in {'doge_research','doge_lab'}:
   self.assertNotIn(too_broad,DEFAULT)

if __name__=='__main__': unittest.main()
