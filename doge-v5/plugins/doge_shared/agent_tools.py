from __future__ import annotations

import json
from pydantic import Field
from pydantic.dataclasses import dataclass
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext
from .academic import AstroService, BioService, MaterialService, PaperService, ResearchChemService, TrialService
from .services import BingService, ChartService, ChemService, CodecService, MathService, NasaService
from .weather import WeatherService
from .lookup import LookupService
from .chaoli import ChaoliService

@dataclass
class DogeMathTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_math"
    description: str = (
        "Doge 数学计算工具：精确/符号代数、微积分、数论、统计、OEIS、Wolfram|Alpha。"
        "数学可视化和模拟属于 /lab；形式化语言的 playground 链接也可由 formal 动作生成。"
    )
    wolfram_appid: str = ""
    parameters: dict = Field(default_factory=lambda: {
        "type":"object",
        "properties":{
            "action":{"type":"string","enum":["calc","base","pi","oeis","numeric","simplify","expand","factor","solve","diff","integrate","limit","factorint","prime","stats","wa","formal"]},
            "input":{"type":"string","description":"表达式、方程、查询或整数；按 action 解释"},
            "variable":{"type":"string","default":"x"},
            "order":{"type":"integer","minimum":1,"maximum":12},
            "digits":{"type":"integer","minimum":2,"maximum":100},
            "lower":{"type":"string"},"upper":{"type":"string"},"point":{"type":"string"},
            "direction":{"type":"string","enum":["+","-","+-"]},
            "values":{"type":"array","items":{"type":"number"},"maxItems":5000},
            "language":{"type":"string","enum":["lean","coq","rocq","rzk"]},
            "code":{"type":"string"},
            "source_base":{"type":"integer","minimum":2,"maximum":64},
            "target_base":{"type":"integer","minimum":2,"maximum":64},
            "start":{"type":"integer","minimum":0},
            "count":{"type":"integer","minimum":1,"maximum":1000}
        },
        "required":["action"]
    })
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        a=str(kwargs.get("action") or ""); q=str(kwargs.get("input") or "")
        if a=="calc": return MathService.calc(q)
        if a=="base": return MathService.base(q,int(kwargs["source_base"]),int(kwargs["target_base"]))
        if a=="pi": return await MathService.pi(int(kwargs.get("start",0)),int(kwargs.get("count",100)))
        if a=="oeis": return await MathService.oeis(q)
        if a=="numeric": return MathService.numeric(q,int(kwargs.get("digits",15)))
        if a in {"simplify","expand","factor"}: return getattr(MathService,a)(q)
        if a=="solve": return MathService.solve(q,str(kwargs.get("variable") or "x"))
        if a=="diff": return MathService.diff(q,str(kwargs.get("variable") or "x"),int(kwargs.get("order",1)))
        if a=="integrate": return MathService.integrate(q,str(kwargs.get("variable") or "x"),kwargs.get("lower"),kwargs.get("upper"))
        if a=="limit": return MathService.limit(q,str(kwargs.get("variable") or "x"),str(kwargs.get("point") or "0"),str(kwargs.get("direction") or "+-"))
        if a=="factorint": return MathService.factorint(int(q))
        if a=="prime": return MathService.prime(int(q))
        if a=="stats": return MathService.stats(list(kwargs.get("values") or []))
        if a=="wa": return await LookupService.wolfram(q,appid=self.wolfram_appid)
        if a=="formal": return MathService.formal(str(kwargs.get("language") or "lean"),str(kwargs.get("code") or q))
        raise ValueError("unknown math action")

@dataclass
class DogeChemTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_chem"
    description: str = "化学科研工具：结构转换、PubChem 规范信息、ChEMBL 药物机制与靶点查询。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"compound":{"type":"string"},"action":{"type":"string","enum":["formula","smiles","names","inchikey","image","info","drug","target"]}},"required":["compound","action"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        action=str(kwargs["action"]); compound=str(kwargs["compound"])
        if action=="info": return await ResearchChemService.info(compound)
        if action=="drug": return await ResearchChemService.drug(compound)
        if action=="target": return await ResearchChemService.target(compound)
        return await ChemService.query(compound,action)

@dataclass
class DogeCodecTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_codec"
    description: str = "URL、Unicode、Hex、Base64 编码或解码。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["encode","decode"]},"kind":{"type":"string","enum":["url","unicode","usc2","hex","base64"]},"text":{"type":"string"}},"required":["action","kind","text"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        return CodecService.run(str(kwargs["action"]),str(kwargs["kind"]),str(kwargs["text"]))

@dataclass
class DogeWeatherTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_weather"
    description: str = "通用天气工具：用 Open-Meteo 查询地点当前天气与 1-7 日预报。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"place":{"type":"string"},"days":{"type":"integer","minimum":1,"maximum":7}},"required":["place"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        data = await WeatherService.forecast(str(kwargs["place"]), int(kwargs.get("days", 3)))
        return WeatherService.format(data)

@dataclass
class DogeNasaTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_nasa_apod"
    description: str = "查询 NASA Astronomy Picture of the Day。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"date":{"type":"string","description":"可选 YYYY-MM-DD"}}})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        return json.dumps(await NasaService.apod(kwargs.get("date") or None),ensure_ascii=False)

@dataclass
class DogeBingTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_bing_wallpaper"
    description: str = "获取 Bing 今日壁纸及说明。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{}})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        return json.dumps(await BingService.today(),ensure_ascii=False)

@dataclass
class DogeChartTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_chart"
    description: str = "把 Chart.js JSON 配置转换为 QuickChart 图片 URL。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"chart_json":{"type":"string"}},"required":["chart_json"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        return ChartService.url(str(kwargs["chart_json"]))

@dataclass
class DogePaperTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_paper"
    description: str = "跨 Crossref/OpenAlex/Unpaywall/DataCite/Europe PMC/arXiv 的论文检索、DOI、引用链、OA、引文格式和撤稿检查。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["search","lookup","cited","refs","related","oa","bib","check","dataset","pubmed","arxiv","author","org","affil"]},"query":{"type":"string"},"style":{"type":"string","enum":["bibtex","ris","apa","gbt"]}},"required":["action","query"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        a=str(kwargs["action"]); q=str(kwargs["query"])
        if a=="search": return await PaperService.search(q)
        if a=="lookup": return await PaperService.lookup(q)
        if a=="cited": return await PaperService.cited(q)
        if a=="refs": return await PaperService.references(q)
        if a=="related": return await PaperService.related(q)
        if a=="oa": return await PaperService.oa(q)
        if a=="bib": return await PaperService.bib(q,str(kwargs.get("style") or "bibtex"))
        if a=="check": return await PaperService.check(q)
        if a=="dataset": return await PaperService.datasets(q)
        if a=="pubmed": return await PaperService.pubmed(q)
        if a=="arxiv": return await PaperService.arxiv(q)
        if a=="author": return await PaperService.author(q)
        if a=="org": return await PaperService.organization(q)
        if a=="affil": return await PaperService.organization(q,affiliation=True)
        raise ValueError("unknown paper action")

@dataclass
class DogeBioTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_bio"
    description: str = "生命科学工具：UniProt、InterPro、Ensembl、RCSB PDB、Reactome、Open Targets 与 UniProt ID mapping。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["protein","domain","gene","pdb","alphafold","variant","pathway","target","map","blast","blastget"]},"query":{"type":"string"},"source":{"type":"string"},"target_db":{"type":"string"},"ids":{"type":"string"}},"required":["action"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        a=str(kwargs["action"]); q=str(kwargs.get("query") or "")
        if a=="protein": return await BioService.protein(q)
        if a=="domain": return await BioService.domains(q)
        if a=="gene": return await BioService.gene(q)
        if a=="pdb": return await BioService.pdb(q)
        if a=="alphafold": return await BioService.alphafold(q)
        if a=="variant": return await BioService.variant(q)
        if a=="blast": return await BioService.blast_submit(q)
        if a=="blastget": return await BioService.blast_get(q)
        if a=="pathway": return await BioService.pathway(q)
        if a=="target": return await BioService.target(q)
        if a=="map": return await BioService.map_ids(str(kwargs.get("source") or ""),str(kwargs.get("target_db") or ""),str(kwargs.get("ids") or q))
        raise ValueError("unknown bio action")

@dataclass
class DogeMaterialTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_materials"
    description: str = "通过标准 OPTIMADE API 查询材料结构或列出材料数据库 provider。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["find","providers"]},"query":{"type":"string"}},"required":["action"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        if kwargs["action"]=="providers": return await MaterialService.providers()
        return await MaterialService.find(str(kwargs.get("query") or ""))

@dataclass
class DogeAstroTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_astro"
    description: str = "天文学工具：SIMBAD 天体对象、NASA Exoplanet Archive 和可选 NASA ADS 文献检索。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["object","exoplanet","ads"]},"query":{"type":"string"}},"required":["action","query"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        a=str(kwargs["action"]); q=str(kwargs["query"])
        if a=="object": return await AstroService.object(q)
        if a=="exoplanet": return await AstroService.exoplanet(q)
        if a=="ads": return await AstroService.ads(q)
        raise ValueError("unknown astro action")

@dataclass
class DogeTrialTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_trials"
    description: str = "ClinicalTrials.gov v2 临床试验搜索和 NCT 详情查询。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["search","get"]},"query":{"type":"string"}},"required":["action","query"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        return await TrialService.get(str(kwargs["query"])) if kwargs["action"]=="get" else await TrialService.search(str(kwargs["query"]))

@dataclass
class DogeLookupTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_lookup"
    description: str = (
        "Grounded 通用查询：百科、Wikidata，以及无需付费 API key 的实时网页检索/公开网页正文提取。"
        "当问题涉及最新进展、近期论文/证明/反例、新闻、当前人物/产品/规则，或你怀疑参数知识可能过时时，优先 action=web 检索后再回答；来源冲突时明确呈现不确定性，不把单条网页当定论。"
    )
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["auto","wiki","entity","web","read","wolfram"]},"query":{"type":"string"},"lang":{"type":"string","default":"zh"},"max_results":{"type":"integer","minimum":2,"maximum":10},"freshness":{"type":"string","description":"可选时效筛选，如 day/week/month/year，按上游支持解释"}},"required":["action","query"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        action=str(kwargs.get("action") or "auto"); query=str(kwargs.get("query") or ""); lang=str(kwargs.get("lang") or "zh")
        if action=="wiki": return (await LookupService.wikipedia(query,lang)).format()
        if action=="entity": return await LookupService.wikidata(query,lang)
        if action=="web": return await LookupService.web_search(query,int(kwargs.get("max_results",6)),str(kwargs.get("freshness") or ""))
        if action=="read": return await LookupService.web_extract(query)
        if action=="wolfram": return await LookupService.wolfram(query)
        return await LookupService.auto(query,lang)

@dataclass
class DogeChaoliTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_chaoli"
    description: str = (
        "超理论坛只读工具。不依赖站内搜索：可读取最新/分板主题流、帖子全文或具体楼层与上下文、"
        "用户公开活动、帖子中的超理引用链和链接预览。遇到超理帖子链接或用户明确询问论坛近期内容时优先使用。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type":"object",
        "properties":{
            "action":{"type":"string","enum":["latest","channel","read","floor","context","outline","user","links","preview","status"]},
            "target":{"type":"string","description":"板块名、帖子号/链接或用户ID/链接，按 action 解释"},
            "floor":{"type":"integer","minimum":1},
            "context":{"type":"integer","minimum":0,"maximum":3},
            "limit":{"type":"integer","minimum":1,"maximum":30}
        },
        "required":["action"]
    })
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        a=str(kwargs.get("action") or ""); target=str(kwargs.get("target") or "").strip()
        if a=="latest": return await ChaoliService.latest("all",int(kwargs.get("limit",10)))
        if a=="channel": return await ChaoliService.latest(target or "all",int(kwargs.get("limit",10)))
        if a=="read": return await ChaoliService.read(target)
        if a=="floor": return await ChaoliService.read(target,int(kwargs.get("floor",1)),0)
        if a=="context": return await ChaoliService.read(target,int(kwargs.get("floor",1)),int(kwargs.get("context",1)))
        if a=="outline": return await ChaoliService.outline(target,int(kwargs.get("limit",40)))
        if a=="user": return await ChaoliService.user(target,int(kwargs.get("limit",8)))
        if a=="links": return await ChaoliService.links(target,int(kwargs.get("limit",12)))
        if a=="preview": return await ChaoliService.preview(target)
        if a=="status": return await ChaoliService.status()
        raise ValueError("unknown chaoli action")

TOOLS=(DogeMathTool,DogeChemTool,DogeCodecTool,DogeWeatherTool,DogeNasaTool,DogeBingTool,DogeChartTool,DogePaperTool,DogeBioTool,DogeMaterialTool,DogeAstroTool,DogeTrialTool,DogeLookupTool,DogeChaoliTool)


def register_domain_tools(context, plugin_name: str, *tools):
    """Register shared tool classes but bind their lifecycle to one Doge plugin.

    AstrBot derives FunctionTool.handler_module_path from the class's Python
    module. Doge intentionally keeps the reusable tool implementations in
    doge_shared, so the automatic path would otherwise make tools survive when
    an individual domain plugin is disabled. Explicitly assigning the real
    plugin module path preserves true plug/unplug semantics.
    """
    context.add_llm_tools(*tools)
    owner = f"data.plugins.{plugin_name}.main"
    for tool in tools:
        tool.handler_module_path = owner
    return tools
