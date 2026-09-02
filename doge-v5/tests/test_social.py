from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

import astrbot.api.message_components as Comp

ROOT=Path(__file__).resolve().parents[1]; PLUGINS=ROOT/'plugins'
if str(PLUGINS) not in sys.path: sys.path.insert(0,str(PLUGINS))
data_pkg=types.ModuleType('data'); data_pkg.__path__=[]
plugins_pkg=types.ModuleType('data.plugins'); plugins_pkg.__path__=[str(PLUGINS)]
data_pkg.plugins=plugins_pkg
sys.modules.setdefault('data',data_pkg); sys.modules.setdefault('data.plugins',plugins_pkg)

from doge_social.main import DogeSocial, _SENTINEL

class Config(dict):
    def __init__(self,*a,**kw): super().__init__(*a,**kw); self.saved=0
    def save_config(self): self.saved += 1

class Ctx:
    def __init__(self, stars): self.stars=stars
    def get_registered_star(self,name): return self.stars.get(name)

class StealCfg:
    def __init__(self):
        self.send_target_whitelist=[f'group:{_SENTINEL}']
        self.steal_target_whitelist=[f'group:{_SENTINEL}']

class Stealer:
    def __init__(self): self.plugin_config=StealCfg(); self.updates=[]
    def update_config(self,d):
        self.updates.append(d.copy())
        for k,v in d.items(): setattr(self.plugin_config,k,v)

class Event:
    def __init__(self,text): self.message_str=text; self.chain=[Comp.Plain(text),Comp.At(qq='123')]
    def get_messages(self): return self.chain

class SocialTests(unittest.TestCase):
    def test_guard_is_fail_closed_and_omits_sentinel_from_status(self):
        self.assertEqual(DogeSocial._real_groups([_SENTINEL,'2','1','2']),['1','2'])
        self.assertEqual(DogeSocial._guarded_groups([]),[_SENTINEL])

    def test_air_group_toggle_updates_upstream_config_and_instance(self):
        engine=SimpleNamespace(enabled_groups=[_SENTINEL], proactive_enabled_groups=[_SENTINEL], enable_group_chat=True, enable_proactive_chat=True)
        meta=SimpleNamespace(config=Config(), star_cls=engine)
        obj=object.__new__(DogeSocial); obj.context=Ctx({'astrbot_plugin_group_chat_plus':meta})
        groups, proactive=obj._set_air_groups('100',True)
        self.assertEqual(groups,['100']); self.assertEqual(proactive,['100'])
        self.assertIn('100',engine.enabled_groups); self.assertIn(_SENTINEL,engine.enabled_groups)
        self.assertEqual(meta.config['decision_ai_provider_id'],'deepseek/deepseek-v4-flash')
        groups,_=obj._set_air_groups('100',False)
        self.assertEqual(groups,[]); self.assertEqual(engine.enabled_groups,[_SENTINEL])

    def test_large_emoji_toggle_delegates_to_tagged_meme_engine(self):
        engine=Stealer(); meta=SimpleNamespace(config=Config(), star_cls=engine)
        obj=object.__new__(DogeSocial); obj.context=Ctx({'astrbot_plugin_stealer':meta})
        self.assertEqual(obj._set_emoji_group('200',True),['200'])
        self.assertEqual(engine.plugin_config.meme_chance,0.22)
        self.assertEqual(engine.plugin_config.vision_provider_id,'deepseek/deepseek-v4-flash-vision-exp')
        self.assertIn('group:200',engine.plugin_config.send_target_whitelist)
        self.assertEqual(obj._set_emoji_group('200',False),[])
        self.assertEqual(engine.plugin_config.send_target_whitelist,[f'group:{_SENTINEL}'])

    def test_meme_event_rewrite_is_scoped_and_restored(self):
        obj=object.__new__(DogeSocial); event=Event('/social meme make 摸头 hello')
        old=[x.text if isinstance(x,Comp.Plain) else None for x in event.chain]
        with obj._meme_event(event,'摸头 hello'):
            self.assertEqual(event.message_str,'摸头 hello')
            self.assertEqual(event.chain[0].text,'摸头 hello')
            self.assertIsInstance(event.chain[1],Comp.At)
        self.assertEqual(event.message_str,'/social meme make 摸头 hello')
        self.assertEqual(event.chain[0].text,old[0])

if __name__=='__main__': unittest.main()
