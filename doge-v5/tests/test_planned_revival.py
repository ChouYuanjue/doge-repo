from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

import astrbot.api.message_components as Comp
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]; PLUGINS=ROOT/'plugins'
if str(PLUGINS) not in sys.path: sys.path.insert(0,str(PLUGINS))
data_pkg=sys.modules.get('data') or types.ModuleType('data'); data_pkg.__path__=[]
plugins_pkg=sys.modules.get('data.plugins') or types.ModuleType('data.plugins'); plugins_pkg.__path__=[str(PLUGINS)]
data_pkg.plugins=plugins_pkg; sys.modules['data']=data_pkg; sys.modules['data.plugins']=plugins_pkg

from doge_memes.main import DogeMemes
from doge_minecraft.main import DogeMinecraft
from doge_minecraft.service import (add_server, cleanup_servers, delete_server, find_server,
                                    migrate_old_format, read_json, render_server_info,
                                    update_server, update_server_status)
from doge_shared.capabilities import match_invocation, registry

class Ctx:
    def __init__(self,meta): self.meta=meta
    def get_registered_star(self,name): return self.meta if name=='astrbot_plugin_meme_generator' else None

class Event:
    def __init__(self,text='/meme 摸头 hello'):
        self.message_str=text; self.chain=[Comp.Plain(text),Comp.At(qq='2')]
    def get_messages(self): return self.chain
    def chain_result(self,chain): return SimpleNamespace(chain=chain,use_markdown=lambda *_:None)
    def is_admin(self): return True

class PlannedRevivalTests(unittest.TestCase):
    def test_manifest_has_no_planned_plugins(self):
        m=json.loads((ROOT/'plugin_manifest.json').read_text(encoding='utf-8'))
        self.assertEqual([x['name'] for x in m['plugins'] if x.get('status')=='planned'],[])
        defaults={x['name'] for x in m['plugins'] if x.get('default')}
        self.assertIn('doge_memes',defaults); self.assertIn('doge_minecraft',defaults)

    def test_meme_generation_reuses_external_engine_and_restores_event(self):
        seen=[]
        class Manager:
            async def generate_meme(self,event): seen.append(event.message_str); return b'png'
        cfg=SimpleNamespace(trigger_prefix='__doge_meme_internal__',is_plugin_enabled=lambda:True)
        engine=SimpleNamespace(meme_config=cfg,meme_manager=Manager())
        obj=object.__new__(DogeMemes); obj.context=Ctx(SimpleNamespace(star_cls=engine))
        event=Event(); result=asyncio.run(obj._generate(event,'摸头 hello'))
        self.assertEqual(seen,['__doge_meme_internal__摸头 hello'])
        self.assertEqual(event.message_str,'/meme 摸头 hello')
        self.assertEqual(event.chain[0].text,'/meme 摸头 hello')
        self.assertEqual(len(result.chain),1)

    def test_old_mc_format_migration_is_not_immediately_cleanup_eligible(self):
        now=2_000_000_000
        old={'MyServer':{'name':'MyServer','host':'example.org'}}
        new=migrate_old_format(old,now=now)
        row=new['servers']['1']
        self.assertEqual(row['created_time'],now)
        self.assertIsNone(row['last_success_time'])

    def test_mc_store_round_trip_and_cleanup_uses_creation_when_never_successful(self):
        async def scenario(td):
            p=Path(td)/'g.json'; now=int(time.time())
            ok,sid=await add_server(p,'A','example.org',initial_success=False); self.assertTrue(ok)
            self.assertEqual(sid,'1')
            data=await read_json(p); self.assertEqual(find_server(data,'A')[1]['host'],'example.org')
            self.assertTrue(await update_server(p,'1',new_name='B',new_host='example.net:25565'))
            self.assertTrue(await update_server_status(p,'1',False))
            data=await read_json(p); self.assertEqual(data['servers']['1']['failed_count'],1)
            self.assertEqual(await cleanup_servers(p,now=now+9*86400),[])
            deleted=await cleanup_servers(p,now=now+11*86400); self.assertEqual([x['name'] for x in deleted],['B'])
        with tempfile.TemporaryDirectory() as td: asyncio.run(scenario(td))

    def test_mc_success_resets_failure_and_protects_cleanup(self):
        async def scenario(td):
            p=Path(td)/'g.json'; ok,_=await add_server(p,'A','example.org',initial_success=False); self.assertTrue(ok)
            await update_server_status(p,'1',False); await update_server_status(p,'1',True)
            d=await read_json(p); self.assertEqual(d['servers']['1']['failed_count'],0); self.assertIsNotNone(d['servers']['1']['last_success_time'])
        with tempfile.TemporaryDirectory() as td: asyncio.run(scenario(td))

    def test_mc_card_renderer_uses_real_font_object_and_png(self):
        data=render_server_info({'players_list':['Alice','张三'],'latency':42,'plays_max':20,'plays_online':2,'server_version':'1.21.8','icon_base64':''},server_name='[1] 测试服')
        with tempfile.NamedTemporaryFile(suffix='.png') as f:
            f.write(data); f.flush()
            with Image.open(f.name) as im: self.assertEqual(im.format,'PNG'); self.assertEqual(im.width,600)


    def test_mc_query_refreshes_live_status_before_cleanup(self):
        from unittest.mock import patch
        event=SimpleNamespace()
        event.get_group_id=lambda:'1'; event.get_sender_id=lambda:'2'
        event.chain_result=lambda chain:SimpleNamespace(chain=chain,use_markdown=lambda *_:None)
        event.plain_result=lambda text:SimpleNamespace(chain=[Comp.Plain(text)],use_markdown=lambda *_:None)
        obj=object.__new__(DogeMinecraft); obj.default_icon=ROOT/'plugins/doge_minecraft/resource/default_icon.png'; obj._path=lambda _event:Path('/tmp/fake-mc.json')
        calls=[]
        data={'servers':{'1':{'id':1,'name':'live','host':'example.org'}}}
        status={'players_list':[],'latency':10,'plays_max':20,'plays_online':0,'server_version':'1.21','icon_base64':''}
        async def fake_read(_): return data
        async def fake_status(_): calls.append('query'); return status
        async def fake_update(*_): calls.append('update'); return True
        async def fake_cleanup(_): calls.append('cleanup'); self.assertIn('update',calls); return []
        async def run():
            with patch('doge_minecraft.main.read_json',fake_read), patch('doge_minecraft.main.get_server_status',fake_status), patch('doge_minecraft.main.update_server_status',fake_update), patch('doge_minecraft.main.cleanup_servers',fake_cleanup):
                out=[]
                async for x in obj._query_all(event): out.append(x)
                return out
        out=asyncio.run(run())
        self.assertEqual(calls[:3],['query','update','cleanup'])
        self.assertEqual(len(out),1)

    def test_formal_registry_prefers_restored_surfaces(self):
        self.assertEqual(match_invocation('/meme 摸头 hello').capability_id,'meme.generate')
        self.assertEqual(match_invocation('/meme detail 摸头').capability_id,'meme.detail')
        self.assertEqual(match_invocation('/mc').capability_id,'minecraft.query')
        self.assertEqual(match_invocation('/mc mcadd test example.org').capability_id,'minecraft.add')
        self.assertEqual(match_invocation('/mc list').capability_id,'minecraft.list')

if __name__=='__main__': unittest.main()
