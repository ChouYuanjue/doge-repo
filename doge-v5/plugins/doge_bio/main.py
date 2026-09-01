from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,register
from data.plugins.doge_shared.agent_tools import DogeBioTool,register_domain_tools
from data.plugins.doge_shared.academic import BioService
from data.plugins.doge_shared.presentation import long_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head
from data.plugins.doge_shared.help_service import format_cli_error

@register('doge_bio','runnel','蛋白、结构、序列、通路与靶点工具','5.3.0')
class DogeBio(Star):
 def __init__(self,context:Context): super().__init__(context); register_domain_tools(context,'doge_bio',DogeBioTool())
 @filter.command('bio')
 async def command(self,event:AstrMessageEvent):
  try:
   p=split_head(command_payload(event.message_str,'bio'),1)
   if len(p)<2:
    yield text_result(event,'`/bio protein|domain|gene|pdb|af|variant|pathway|target|map|blast|blastget ...`'); return
   a,q=p[0].lower(),p[1].strip()
   if a in {'protein','uniprot'}: r=await BioService.protein(q)
   elif a in {'domain','interpro'}: r=await BioService.domains(q)
   elif a in {'gene','ensembl'}: r=await BioService.gene(q)
   elif a in {'pdb','structure'}: r=await BioService.pdb(q)
   elif a in {'af','alphafold'}: r=await BioService.alphafold(q)
   elif a in {'variant','var'}: r=await BioService.variant(q)
   elif a=='blast': r=await BioService.blast_submit(q)
   elif a in {'blastget','blast_get'}: r=await BioService.blast_get(q)
   elif a in {'pathway','reactome'}: r=await BioService.pathway(q)
   elif a in {'target','opentargets'}: r=await BioService.target(q)
   elif a=='map':
    x=split_head(q,2)
    if len(x)<3: raise ValueError('用法：/bio map <from> <to> <IDs>')
    r=await BioService.map_ids(x[0],x[1],x[2])
   else: raise ValueError('未知 bio 子命令')
   yield long_result(event,'Bio',r,fold_threshold=1400)
  except Exception as e: logger.warning(f'doge bio failed: {e}'); yield text_result(event,format_cli_error('bio', e),markdown=False)
