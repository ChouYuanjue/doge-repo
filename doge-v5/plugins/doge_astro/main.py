from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,register
from data.plugins.doge_shared.agent_tools import DogeAstroTool,register_domain_tools
from data.plugins.doge_shared.academic import AstroService
from data.plugins.doge_shared.presentation import long_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head
@register('doge_astro','runnel','天体、系外行星与 ADS 工具','5.3.0')
class DogeAstro(Star):
 def __init__(self,context:Context): super().__init__(context); register_domain_tools(context,'doge_astro',DogeAstroTool())
 @filter.command('astro')
 async def command(self,event:AstrMessageEvent):
  try:
   p=split_head(command_payload(event.message_str,'astro'),1)
   if len(p)<2: yield text_result(event,'`/astro object <SIMBAD>` · `exo <query>` · `ads <query>`'); return
   a,q=p[0].lower(),p[1].strip()
   if a in {'object','simbad'}: r=await AstroService.object(q)
   elif a in {'exo','exoplanet'}: r=await AstroService.exoplanet(q)
   elif a in {'ads','paper'}: r=await AstroService.ads(q)
   else: raise ValueError('未知 astro 子命令')
   yield long_result(event,'Astro',r,fold_threshold=1400)
  except Exception as e: yield text_result(event,f'astro 失败：{e}',markdown=False)
