from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent,filter
from astrbot.api.star import Context,Star,register
from data.plugins.doge_shared.agent_tools import DogePaperTool,register_domain_tools
from data.plugins.doge_shared.academic import PaperService
from data.plugins.doge_shared.presentation import long_result,text_result
from data.plugins.doge_shared.raw_command import command_payload,split_head

@register('doge_papers','runnel','论文发现、引用链、开放全文与引文信息','5.3.0')
class DogePapers(Star):
 def __init__(self,context:Context): super().__init__(context); register_domain_tools(context,'doge_papers',DogePaperTool())
 @filter.command('paper')
 async def command(self,event:AstrMessageEvent):
  try:
   p=split_head(command_payload(event.message_str,'paper'),1)
   if len(p)<2:
    yield text_result(event,'`/paper search|doi|cited|refs|related|oa|bib|check|dataset|pubmed|arxiv|author|org|affil <query>`'); return
   a,q=p[0].lower(),p[1].strip()
   if a=='search': r=await PaperService.search(q)
   elif a in {'doi','get','lookup'}: r=await PaperService.lookup(q)
   elif a in {'cited','cites'}: r=await PaperService.cited(q)
   elif a in {'refs','references'}: r=await PaperService.references(q)
   elif a in {'related','similar'}: r=await PaperService.related(q)
   elif a in {'oa','open'}: r=await PaperService.oa(q)
   elif a=='bib':
    x=split_head(q,1); r=await PaperService.bib(x[0],x[1] if len(x)>1 else 'bibtex')
   elif a in {'check','retract','retraction'}: r=await PaperService.check(q)
   elif a in {'dataset','data'}: r=await PaperService.datasets(q)
   elif a in {'pubmed','pmc'}: r=await PaperService.pubmed(q)
   elif a=='arxiv': r=await PaperService.arxiv(q)
   elif a=='author': r=await PaperService.author(q)
   elif a in {'org','institution'}: r=await PaperService.organization(q)
   elif a in {'affil','affiliation'}: r=await PaperService.organization(q,affiliation=True)
   else: raise ValueError('未知 paper 子命令')
   yield long_result(event,'Paper',r,fold_threshold=1400)
  except Exception as e: logger.warning(f'doge paper failed: {e}'); yield text_result(event,f'paper 失败：{e}',markdown=False)
