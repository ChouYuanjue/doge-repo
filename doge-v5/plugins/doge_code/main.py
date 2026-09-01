from __future__ import annotations

import html
import json
import re
import time

import aiohttp
from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,register
from data.plugins.doge_shared.presentation import long_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head

LANGUAGES={
 'python':(0,'py'),'py':(0,'py'),'javascript':(1,'js'),'js':(1,'js'),
 'cpp':(2,'cpp'),'c++':(2,'cpp'),'c':(3,'c'),'java':(4,'java'),
 'html':(5,'html'),'css':(6,'css'),'php':(7,'php'),'go':(8,'go'),
 'golang':(8,'go'),'ruby':(9,'rb'),'swift':(10,'swift'),'kotlin':(11,'kt'),
}

class RunoobExecutor:
 MAIN='https://www.runoob.com/try/runcode.php?filename=helloworld&type=python'
 COMPILE='https://www.runoob.com/try/compile2.php'
 def __init__(self): self.token=None; self.expires=0.0
 async def get_token(self):
  if self.token and time.monotonic()<self.expires: return self.token
  timeout=aiohttp.ClientTimeout(total=15)
  async with aiohttp.ClientSession(timeout=timeout,headers={'User-Agent':'Doge-v5/5.3'}) as s:
   async with s.get(self.MAIN) as r:
    r.raise_for_status(); page=await r.text()
  # Keep only the current hidden-field form plus conservative JS fallbacks.
  patterns=[r'id=["\']token["\'][^>]*value=["\']([^"\']+)',r'name=["\']token["\'][^>]*value=["\']([^"\']+)',r'\btoken\s*=\s*["\']([^"\']+)']
  for pat in patterns:
   m=re.search(pat,page,re.I)
   if m:
    self.token=m.group(1); self.expires=time.monotonic()+1800; return self.token
  raise RuntimeError('Runoob token format changed')
 async def execute(self,language,code):
  if language not in LANGUAGES: raise ValueError('不支持的语言：'+language)
  if len(code)>12000: raise ValueError('代码最多 12000 字符')
  typ,ext=LANGUAGES[language]; token=await self.get_token()
  data={'code':code,'token':token,'language':typ,'fileext':ext,'filename':f'main.{ext}'}
  timeout=aiohttp.ClientTimeout(total=25)
  async with aiohttp.ClientSession(timeout=timeout,headers={'User-Agent':'Doge-v5/5.3'}) as s:
   async with s.post(self.COMPILE,data=data) as r:
    r.raise_for_status(); raw=await r.text()
  try: obj=json.loads(raw)
  except json.JSONDecodeError: return raw.strip()[:12000] or '执行完成，无输出。'
  error=str(obj.get('error') or obj.get('errors') or '').strip()
  output=str(obj.get('output') or '').strip()
  text=('执行错误：\n'+error) if error else (output or '执行完成，无输出。')
  return html.unescape(text)[:12000]

@register('doge_code','runnel','远端代码执行（当前使用 Runoob，不在宿主机执行）','5.3.0')
class DogeCode(Star):
 def __init__(self,context:Context): super().__init__(context); self.executor=RunoobExecutor()
 @filter.command('run')
 async def run(self,event:AstrMessageEvent):
  try:
   payload=command_payload(event.message_str,'run'); p=split_head(payload,1)
   if len(p)<2:
    yield text_result(event,'`/run <python|js|cpp|c|java|go|ruby|swift|kotlin|php> <代码>`\n代码发送到 Runoob 远端执行器，不会在 Doge 宿主机执行。'); return
   lang=p[0].lower(); code=p[1]
   result=await self.executor.execute(lang,code)
   yield long_result(event,f'Run · {lang}',f'```\n{result}\n```',fold_threshold=1800)
  except Exception as e: yield text_result(event,f'run 失败：{e}',markdown=False)
