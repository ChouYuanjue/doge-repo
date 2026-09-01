from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,register
from data.plugins.doge_shared.agent_tools import DogeTrialTool,register_domain_tools
from data.plugins.doge_shared.academic import TrialService
from data.plugins.doge_shared.presentation import long_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head
from data.plugins.doge_shared.help_service import format_cli_error
@register('doge_clinical','runnel','ClinicalTrials.gov 临床试验工具','5.3.0')
class DogeClinical(Star):
 def __init__(self,context:Context): super().__init__(context); register_domain_tools(context,'doge_clinical',DogeTrialTool())
 @filter.command('trial')
 async def command(self,event:AstrMessageEvent):
  try:
   raw=command_payload(event.message_str,'trial'); p=split_head(raw,1)
   if not p: yield text_result(event,'`/trial search <query>` · `/trial get <NCT ID>`'); return
   a=p[0]; q=p[1].strip() if len(p)>1 else ''
   if a.lower() in {'get','show'}: r=await TrialService.get(q)
   elif a.lower() in {'search','find'}: r=await TrialService.search(q)
   else: r=await TrialService.get(a) if a.upper().startswith('NCT') else await TrialService.search(raw)
   yield long_result(event,'Clinical Trials',r,fold_threshold=1400)
  except Exception as e: yield text_result(event,format_cli_error('trial', e),markdown=False)
