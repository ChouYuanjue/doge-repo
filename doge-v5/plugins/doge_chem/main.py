from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register
from data.plugins.doge_shared.agent_tools import DogeChemTool,register_domain_tools
from data.plugins.doge_shared.academic import ResearchChemService
from data.plugins.doge_shared.services import ChemService
from data.plugins.doge_shared.presentation import image_result,long_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head
from data.plugins.doge_shared.help_service import format_cli_error

@register('doge_chem','runnel','化学结构、PubChem 与 ChEMBL','5.3.0')
class DogeChem(Star):
 def __init__(self,context:Context): super().__init__(context); register_domain_tools(context,'doge_chem',DogeChemTool())
 @filter.command('chem')
 async def command(self,event:AstrMessageEvent):
  try:
   p=split_head(command_payload(event.message_str,'chem'),1)
   if len(p)<2:
    yield text_result(event,'`/chem <formula|smiles|names|inchikey|image|info|drug|target> <查询>`'); return
   a,q=p[0].lower(),p[1]
   if a=='info': r=await ResearchChemService.info(q)
   elif a=='drug': r=await ResearchChemService.drug(q)
   elif a=='target': r=await ResearchChemService.target(q)
   else: r=await ChemService.query(q,a)
   yield image_result(event,r,q,remote=True) if a=='image' else long_result(event,'Chem',r,fold_threshold=1400)
  except Exception as e: yield text_result(event,format_cli_error('chem', e),markdown=False)
