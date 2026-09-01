from __future__ import annotations
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,StarTools,register
import astrbot.api.message_components as Comp
from data.plugins.doge_shared.arena import ArenaStore,draw,judge_prompts,scene
from data.plugins.doge_shared.presentation import mention_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head

@register('doge_arena','runnel','Doge 荒诞能力竞技场','5.3.0')
class DogeArena(Star):
 def __init__(self,context:Context): super().__init__(context); self.context=context; self.store=ArenaStore(StarTools.get_data_dir('doge_arena')/'arena.json')
 @filter.command('arena')
 async def arena(self,event:AstrMessageEvent):
  try:
   payload=command_payload(event.message_str,'arena'); p=split_head(payload,1); action=p[0].lower() if p else 'draw'; scope=event.unified_msg_origin; uid=str(event.get_sender_id())
   if action in {'draw','get','reroll'}:
    card=draw(); self.store.set(scope,uid,card); yield text_result(event,'🎴 你的本轮能力卡\n'+card.render(),markdown=False); return
   if action=='show':
    card=self.store.get(scope,uid); yield text_result(event,card.render() if card else '你还没有能力卡。使用 /arena draw',markdown=False); return
   if action not in {'fight','duel'}: raise ValueError('用法：/arena draw | show | fight @某人')
   target=None; tname=None
   for seg in event.get_messages():
    if isinstance(seg,Comp.At): target=str(seg.qq); tname=str(getattr(seg,'name','') or '') or None; break
   rest=p[1].strip() if len(p)>1 else ''
   if not target and rest.isdigit(): target=rest
   if not target: raise ValueError('请指定对手，例如 /arena fight @某人')
   if target==uid: raise ValueError('不能和自己打')
   mine=self.store.get(scope,uid); theirs=self.store.get(scope,target)
   if not mine: raise ValueError('你还没有能力卡，先 /arena draw')
   if not theirs: raise ValueError('对手还没有能力卡')
   battlefield=scene(); provider=await self.context.get_using_provider_async(umo=scope)
   if not provider: raise ValueError('竞技场裁判需要聊天模型 provider')
   a=event.get_sender_name() or uid; b=tname or f'玩家{target}'; system,prompt=judge_prompts(a,mine,b,theirs,battlefield); resp=await provider.text_chat(prompt=prompt,system_prompt=system)
   result=(resp.completion_text or '').strip()
   if not result: raise ValueError('裁判没有给出结果')
   yield mention_result(event,target,'⚔️ 荒诞能力竞技场\n'+battlefield.render()+'\n\n'+result,target_label=f'对手：{b}')
  except Exception as e: logger.warning(f'doge arena failed: {e}'); yield text_result(event,f'arena 失败：{e}',markdown=False)
