from __future__ import annotations

import asyncio
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]; PLUGINS=ROOT/'plugins'
if str(PLUGINS) not in sys.path: sys.path.insert(0,str(PLUGINS))
data_pkg=sys.modules.get('data') or types.ModuleType('data'); data_pkg.__path__=[]
plugins_pkg=sys.modules.get('data.plugins') or types.ModuleType('data.plugins'); plugins_pkg.__path__=[str(PLUGINS)]
data_pkg.plugins=plugins_pkg; sys.modules['data']=data_pkg; sys.modules['data.plugins']=plugins_pkg

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.star.filter.command_group import CommandGroupFilter
from doge_shared.agent_tools import DogeEmojiSearchTool, DogeEmojiSendTool, DogeEmojiStealTool, DogeMemeTool
from doge_shared.capabilities import match_invocation, registry, search_capabilities
from doge_shared.media_namespace import is_stealer_meme_root, remove_stealer_meme_command_group, strip_legacy_stealer_tools


def bare(name):
    return FunctionTool(name=name,description=name,parameters={'type':'object','properties':{}})


class MediaNamespaceTests(unittest.TestCase):
    def test_agent_tool_names_are_semantically_separate(self):
        self.assertEqual(DogeMemeTool().name,'doge_meme')
        self.assertEqual(DogeEmojiSearchTool().name,'search_emoji')
        self.assertEqual(DogeEmojiSendTool().name,'send_emoji')
        self.assertEqual(DogeEmojiStealTool().name,'steal_emoji')
        self.assertIn('固定模板',DogeMemeTool().description)
        self.assertIn('不是模板 meme',DogeEmojiSearchTool().description)

    def test_old_stealer_names_are_removed_from_each_agent_request(self):
        tools=ToolSet([bare('search_meme'),bare('send_meme'),bare('steal_meme'),bare('doge_meme'),bare('search_emoji')])
        removed=strip_legacy_stealer_tools(tools)
        self.assertEqual(removed,['search_meme','send_meme','steal_meme'])
        self.assertEqual(set(tools.names()),{'doge_meme','search_emoji'})

    def test_only_upstream_stealer_meme_root_is_pruned(self):
        stealer=SimpleNamespace(handler_module_path='data.plugins.astrbot_plugin_stealer.main',event_filters=[CommandGroupFilter('meme')])
        doge=SimpleNamespace(handler_module_path='data.plugins.doge_memes.main',event_filters=[CommandGroupFilter('meme')])
        other=SimpleNamespace(handler_module_path='data.plugins.astrbot_plugin_stealer.main',event_filters=[CommandGroupFilter('emoji')])
        self.assertTrue(is_stealer_meme_root(stealer))
        self.assertFalse(is_stealer_meme_root(doge)); self.assertFalse(is_stealer_meme_root(other))
        registry_list=[stealer,doge,other]
        self.assertEqual(remove_stealer_meme_command_group(registry_list),1)
        self.assertEqual(registry_list,[doge,other])

    def test_registry_has_no_transitional_social_meme_surface(self):
        ids={x['id'] for x in registry()['operations']}
        self.assertFalse(any(x.startswith('social.meme') for x in ids))
        self.assertIn('meme.generate',ids)
        self.assertIn('social.emoji.list',ids)
        self.assertEqual(match_invocation('/meme 摸头').capability_id,'meme.generate')
        self.assertEqual(match_invocation('/social emoji list happy 10 1').capability_id,'social.emoji.list')

    def test_capability_search_distinguishes_template_meme(self):
        rows=search_capabilities('摸头 meme',5)
        self.assertTrue(rows)
        self.assertEqual(rows[0]['id'],'meme.generate')

    def test_doge_meme_tool_delegates_to_formal_meme_not_emoji(self):
        calls=[]
        async def fake_exec(_ctx,cmd): calls.append(cmd); return 'ok'
        with patch('doge_shared.agent_tools.execute_formal_command',fake_exec):
            out=asyncio.run(DogeMemeTool().call(SimpleNamespace(),action='generate',template='摸头',text='hello'))
        self.assertEqual(out,'ok')
        self.assertEqual(calls,['/meme 摸头 hello'])

    def test_search_emoji_wraps_upstream_but_explains_disabled_scope(self):
        class Engine:
            async def search_meme(self,event,query):
                yield '搜索失败：当前群聊已禁用表情包功能'
        class Plugins:
            def get_registered_star(self,name):
                return SimpleNamespace(star_cls=Engine()) if name=='astrbot_plugin_stealer' else None
        ctx=SimpleNamespace(context=SimpleNamespace(context=Plugins(),event=object()))
        text=asyncio.run(DogeEmojiSearchTool().call(ctx,query='猫猫'))
        self.assertIn('大表情/贴纸库功能',text)
        self.assertIn('/meme 模板生成器不受影响',text)
        self.assertNotIn('search_meme',text)


if __name__=='__main__': unittest.main()
