from __future__ import annotations
import asyncio,hashlib
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,StarTools,register
from data.plugins.doge_shared.alchemy import AlchemyBook,parse as parse_fusion,prompts as fusion_prompts,split_recipe
from data.plugins.doge_shared.presentation import text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head

@register('doge_alchemy','runnel','Doge 概念炼金与群聊生成设定图鉴','5.6.0')
class DogeAlchemy(Star):
 def __init__(self,context:Context): super().__init__(context); self.context=context; self.data_dir=StarTools.get_data_dir('doge_alchemy'); self.books={}; self.locks={}
 def book(self,scope):
  if scope not in self.books:
   slug=hashlib.sha256(scope.encode()).hexdigest()[:20]; self.books[scope]=AlchemyBook(self.data_dir/'alchemy'/f'{slug}.json')
  return self.books[scope]
 def lock(self,scope):
  if scope not in self.locks: self.locks[scope]=asyncio.Lock()
  return self.locks[scope]
 @filter.command('fuse')
 async def fuse(self,event:AstrMessageEvent):
  try:
   payload=command_payload(event.message_str,'fuse'); scope=event.unified_msg_origin; book=self.book(scope)
   if not payload.strip(): yield text_result(event,'/fuse <素材A> + <素材B> · /fuse book [数量]\n炼金结果由聊天模型生成并作为群聊虚构设定保存，不是现实知识检索。',markdown=False); return
   head=split_head(payload,1)
   if head[0].lower()=='book':
    n=max(1,min(30,int(head[1].strip()))) if len(head)>1 and head[1].strip() else 10; items=book.recent(n)
    if not items: yield text_result(event,'炼金图鉴还是空的。试试 `/fuse 雨天 + 数据库`'); return
    yield text_result(event,f'Doge 炼金图鉴 · 生成设定 {book.count()} 项\n群聊虚构设定，不是现实知识库。\n\n'+'\n'.join(f'{x.emoji} {x.name}〔{x.left} + {x.right}〕' for x in items),markdown=False); return
   left,right=split_recipe(payload); existing=book.get(left,right)
   if existing: yield text_result(event,existing.render(rediscovered=True),markdown=False); return
   async with self.lock(scope):
    existing=book.get(left,right)
    if existing: yield text_result(event,existing.render(rediscovered=True),markdown=False); return
    provider=await self.context.get_using_provider_async(umo=scope)
    if not provider: raise ValueError('炼金炉需要可用的聊天模型 provider')
    system,prompt=fusion_prompts(left,right,book.names()); resp=await provider.text_chat(prompt=prompt,system_prompt=system)
    d=book.add(parse_fusion(resp.completion_text or '',left,right,event.get_sender_id()))
   yield text_result(event,d.render(),markdown=False)
  except Exception as e: logger.warning(f'doge fuse failed: {e}'); yield text_result(event,f'fuse 失败：{e}',markdown=False)
