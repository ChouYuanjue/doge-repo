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

@dataclass
class DogeMathTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_math"
    description: str = "Doge 数学工具：安全算式、进制转换、π 数位和 OEIS 查询。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["calc","base","pi","oeis"]},"input":{"type":"string"},"source_base":{"type":"integer","minimum":2,"maximum":64},"target_base":{"type":"integer","minimum":2,"maximum":64},"start":{"type":"integer","minimum":0},"count":{"type":"integer","minimum":1,"maximum":1000}},"required":["action"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        action=kwargs.get("action","")
        if action=="calc": return MathService.calc(str(kwargs.get("input","")))
        if action=="base": return MathService.base(str(kwargs.get("input","")),int(kwargs["source_base"]),int(kwargs["target_base"]))
        if action=="pi": return await MathService.pi(int(kwargs.get("start",0)),int(kwargs.get("count",100)))
        if action=="oeis": return await MathService.oeis(str(kwargs.get("input","")))
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
    description: str = "Grounded 通用查询：Wikipedia 摘要、Wikidata 结构化实体事实，以及可选 Wolfram|Alpha LLM API。"
    parameters: dict = Field(default_factory=lambda: {"type":"object","properties":{"action":{"type":"string","enum":["auto","wiki","entity","wolfram"]},"query":{"type":"string"},"lang":{"type":"string","default":"zh"}},"required":["action","query"]})
    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        action=str(kwargs.get("action") or "auto"); query=str(kwargs.get("query") or ""); lang=str(kwargs.get("lang") or "zh")
        if action=="wiki": return (await LookupService.wikipedia(query,lang)).format()
        if action=="entity": return await LookupService.wikidata(query,lang)
        if action=="wolfram": return await LookupService.wolfram(query)
        return await LookupService.auto(query,lang)

TOOLS=(DogeMathTool,DogeChemTool,DogeCodecTool,DogeWeatherTool,DogeNasaTool,DogeBingTool,DogeChartTool,DogePaperTool,DogeBioTool,DogeMaterialTool,DogeAstroTool,DogeTrialTool,DogeLookupTool)


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
