from __future__ import annotations
import asyncio
from pathlib import Path
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from data.plugins.doge_shared.presentation import image_result, text_result
from data.plugins.doge_shared.raw_command import command_payload, split_head
from .ai_lab import AILabError, render_bpe, render_grad
HELP=("Doge AI Lab /ai\n"
"  /ai grad <expr> | x=2 y=3      micrograd 计算图 + 反向梯度\n"
"  /ai bpe [merges] <text>        minBPE byte-level merge/token 可视化\n"
"示例：/ai grad relu(x*y + x**2) | x=2 y=-1\n"
"示例：/ai bpe 24 大模型 tokenizer 为什么会把中文拆成奇怪的块")
@register("doge_ai","runnel","轻量 AI 内部机制实验室：autograd 与 BPE","5.4.0")
class DogeAI(Star):
 def __init__(self,context:Context): super().__init__(context); self.data_dir=StarTools.get_data_dir("doge_ai")
 @filter.command("ai")
 async def ai(self,event:AstrMessageEvent):
  path=None
  try:
   payload=command_payload(event.message_str,"ai")
   if not payload.strip() or payload.strip().lower() in {"help","?"}: yield text_result(event,HELP,markdown=False); return
   parts=split_head(payload,1); action=parts[0].lower(); rest=parts[1] if len(parts)>1 else ""
   if action=="grad":
    if not rest.strip(): raise AILabError("用法：/ai grad <expr> | x=2 y=3")
    expr,sep,assign_text=rest.partition("|"); assigns={}
    if sep:
     for item in assign_text.split():
      if "=" not in item: raise AILabError("变量赋值格式应为 x=2")
      k,v=item.split("=",1)
      if not k.isidentifier() or k=="relu": raise AILabError(f"非法变量名：{k}")
      assigns[k]=float(v)
    path,caption=await asyncio.to_thread(render_grad,self.data_dir,expr,assigns); yield image_result(event,path,caption); return
   if action=="bpe":
    if not rest.strip(): raise AILabError("用法：/ai bpe [merges] <text>")
    p=split_head(rest,1); merges=20; text=rest
    if p and p[0].isdigit(): merges=int(p[0]); text=p[1] if len(p)>1 else ""
    path,caption=await asyncio.to_thread(render_bpe,self.data_dir,text,merges); yield image_result(event,path,caption); return
   raise AILabError("未知 AI 子命令。\n"+HELP)
  except (AILabError,ValueError) as exc: yield text_result(event,f"ai 失败：{exc}",markdown=False)
  finally:
   if path is not None: Path(path).unlink(missing_ok=True)
