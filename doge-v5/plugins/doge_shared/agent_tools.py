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
from .agent_bridge import DogePresentTool, execute_formal_command

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
class DogeCthuvianTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_cthuvian"
    description: str = (
        "低延迟 RC-1 Cthuvian/R'lyehian 翻译工具。正向 low/high 的 text 必须是你在当前 Agent 推理中自己忠实翻好的英文；"
        "不要为翻英文再调用任何模型、翻译工具或 capability_search。high 会本地复用已知词，所有未见英文词一次结构化批量造词并原子入表。"
        "from 用于 RC-1→English gloss。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["low", "high", "from"]},
            "text": {
                "type": "string",
                "description": "low/high: Agent 自己翻译后的 English；from: RC-1/Cthuvian 原文",
            },
        },
        "required": ["action", "text"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        action = str(kwargs.get("action") or "").strip().lower()
        text = str(kwargs.get("text") or "").strip()
        if action not in {"low", "high", "from"}:
            raise ValueError("unknown Cthuvian action")
        if not text:
            raise ValueError("Cthuvian text is empty")
        command_action = "to" if action == "low" else action
        return await execute_formal_command(context, f"/lang cthuvian {command_action} {text}")


def _external_star_from_run_context(context, name: str):
    plugin_context = context.context.context
    meta = plugin_context.get_registered_star(name)
    engine = getattr(meta, "star_cls", None) if meta else None
    if engine is None:
        raise RuntimeError(f"required upstream plugin is not loaded: {name}")
    return engine


async def _collect_external_tool(iterator) -> str:
    chunks: list[str] = []
    async for item in iterator:
        if item is not None:
            chunks.append(str(item))
    return "\n".join(x for x in chunks if x).strip()


def _emoji_tool_text(text: str) -> str:
    text = str(text or "")
    text = text.replace("表情包功能", "大表情/贴纸库功能")
    text = text.replace("表情包候选", "大表情/贴纸候选")
    text = text.replace("候选表情包", "候选大表情/贴纸")
    text = text.replace("表情包列表", "大表情/贴纸列表")
    text = text.replace("表情包文件", "大表情/贴纸文件")
    text = text.replace("表情包", "大表情/贴纸")
    return text


@dataclass
class DogeMemeTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_meme"
    description: str = (
        "固定模板 meme 生成工具，例如‘摸头 meme’、‘鲁迅说’、‘结婚申请’。用户要求制作/发送 meme 时直接 action=generate，"
        "不要把 action=detail 当生成前置步骤。生成器会自动解析当前/引用图片、显式 @ 用户头像；图片仍不足时会自动获取当前发送者 QQ 头像，必要时再补 Bot 头像，"
        "因此不要要求用户重复提供这些运行时已经能取得的素材。它与群聊收集的 emoji/sticker 库完全独立。生成成功后工具会直接发送图片并结束本轮。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["generate", "detail", "list", "status"], "description": "制作/发送 meme 必须用 generate；detail 只用于用户明确询问模板参数时。"},
            "template": {"type": "string", "description": "generate/detail 时的模板关键词，例如 摸头"},
            "text": {"type": "string", "description": "generate 时可选文字参数，多个参数按空格保留"},
            "page": {"type": "integer", "minimum": 1},
        },
        "required": ["action"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        action = str(kwargs.get("action") or "generate").strip().lower()
        template = str(kwargs.get("template") or "").strip()
        text = str(kwargs.get("text") or "").strip()
        if action == "generate":
            if not template:
                raise ValueError("meme template keyword is empty")
            payload = template + ((" " + text) if text else "")
            raw = await execute_formal_command(context, f"/meme {payload}")
            try:
                data = json.loads(raw)
                ids = [
                    str(item.get("id"))
                    for item in (data.get("media") or [])
                    if isinstance(item, dict) and item.get("type") == "image" and item.get("id")
                ]
            except Exception:
                ids = []
            if ids:
                # A template-generation request has one unambiguous user-visible
                # result. Send it immediately and terminate the Agent turn instead
                # of asking the model to make another presentation decision.
                return await DogePresentTool().call(context, asset_ids=ids)
            return raw
        if action == "detail":
            if not template:
                raise ValueError("meme template keyword is empty")
            raw = await execute_formal_command(context, f"/meme detail {template}")
            try:
                data = json.loads(raw)
                data["next_step"] = (
                    "If the current user asked to MAKE/SEND this meme, call doge_meme again with action=generate now. "
                    "Do not ask them for an avatar or image that the generator can resolve automatically from current/reply media, explicit mentions, or the current sender's QQ avatar."
                )
                return json.dumps(data, ensure_ascii=False)
            except Exception:
                return raw + "\nIf this is a generation request, call action=generate now; retrievable avatars/media do not need to be requested from the user."
        if action == "list":
            page = max(1, int(kwargs.get("page", 1)))
            return await execute_formal_command(context, f"/meme list {page}")
        if action == "status":
            return await execute_formal_command(context, "/meme status")
        raise ValueError("unknown meme action")


@dataclass
class DogeEmojiSearchTool(FunctionTool[AstrAgentContext]):
    name: str = "search_emoji"
    description: str = (
        "从当前群允许使用的‘已收集 QQ 大表情/贴纸库’中按角色、图上文字、情绪或画面检索候选。"
        "这是 emoji/sticker 库，不是模板 meme 生成器；用户说‘某某 meme/模板表情’时应使用 doge_meme，而不是本工具。"
        "搜索成功后用 send_emoji 发送候选编号。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "2-8 个检索词，如 猫猫 震惊 怎么会这样"}},
        "required": ["query"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        engine = _external_star_from_run_context(context, "astrbot_plugin_stealer")
        event = context.context.event
        text = await _collect_external_tool(engine.search_emoji(event, str(kwargs.get("query") or "")))
        text = _emoji_tool_text(text)
        if "已禁用大表情/贴纸库功能" in text:
            text += "\n这只表示当前会话的 emoji/sticker 库关闭；/meme 模板生成器不受影响。"
        return text


@dataclass
class DogeEmojiSendTool(FunctionTool[AstrAgentContext]):
    name: str = "send_emoji"
    description: str = (
        "发送 search_emoji 返回的已收集 QQ 大表情/贴纸候选。只接受候选编号；"
        "不要用于 meme-generator 模板生成。成功时图片已直接发送，本工具会终止当前 Agent 回复。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {"emoji_id": {"type": "integer", "minimum": 1}},
        "required": ["emoji_id"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs):
        engine = _external_star_from_run_context(context, "astrbot_plugin_stealer")
        event = context.context.event
        text = _emoji_tool_text(await _collect_external_tool(engine.send_emoji(event, int(kwargs.get("emoji_id")))))
        if "发送成功" in text:
            return None
        return text


@dataclass
class DogeEmojiStealTool(FunctionTool[AstrAgentContext]):
    name: str = "steal_emoji"
    description: str = (
        "把当前消息中的一张图片收进 QQ 大表情/贴纸库，并由现有视觉模型自动打标签。"
        "只用于收藏 sticker/emoji 素材，不是模板 meme 生成。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {"image_ref": {"type": "string", "description": "当前消息已有图片 URL 或文件路径"}},
        "required": ["image_ref"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        engine = _external_star_from_run_context(context, "astrbot_plugin_stealer")
        event = context.context.event
        return _emoji_tool_text(await _collect_external_tool(engine.steal_emoji(event, str(kwargs.get("image_ref") or ""))))


@dataclass
class DogePixivTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_pixiv"
    description: str = (
        "Pixiv 插画搜索工具。通过 Doge 的 /pixiv 正式能力搜索标签、随机插画或指定画师 UID。"
        "固定关闭 R18 并过滤 AI 生成作品；服务器主链使用 Lolicon 元数据与可达图片镜像。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["search", "random", "artist"]},
            "query": {"type": "string", "description": "search 时的标签/关键词"},
            "uid": {"type": "string", "description": "artist 时的 Pixiv 画师 UID"},
            "count": {"type": "integer", "minimum": 1, "maximum": 5},
        },
        "required": ["action"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        action = str(kwargs.get("action") or "").strip().lower()
        count = max(1, min(int(kwargs.get("count", 1)), 5))
        if action == "search":
            query = str(kwargs.get("query") or "").strip()
            if not query:
                raise ValueError("pixiv search query is empty")
            return await execute_formal_command(context, f"/pixiv {query} {count}")
        if action == "random":
            return await execute_formal_command(context, f"/pixiv random {count}")
        if action == "artist":
            uid = str(kwargs.get("uid") or "").strip()
            if not uid.isdigit():
                raise ValueError("pixiv artist uid must be numeric")
            return await execute_formal_command(context, f"/pixiv artist {uid} {count}")
        raise ValueError("unknown pixiv action")

@dataclass
class DogeChaoliTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_chaoli"
    description: str = (
        "超理论坛工具：读取时所有作者/板块/楼层/用户字段都要求和同一论坛 DOM 实体强绑定；引用与作者本人正文分离，不能据摘要或相邻元素推断。"
        "支持论坛原生 POST AJAX 搜索、最新/分板主题、帖子/楼层、严格用户名验证、用户公开活动、引用链和链接预览；daily 只查看日报，daily_push 才会真正主动发送日报到当前群。"
        "如果用户给出含 /pN#pPOSTID 或 /conversation/post/POSTID 的具体楼层链接，必须把原链接原样传给 read/preview；不要先 outline、不要改写 permalink、不要自己猜楼号。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type":"object",
        "properties":{
            "action":{"type":"string","enum":["search","daily","daily_push","latest","channel","read","floor","context","outline","user","links","preview","status"]},
            "target":{"type":"string","description":"板块名、帖子号/完整链接或用户名/用户ID/用户链接，按 action 解释；具体楼层 URL 必须保留 #p... 锚点"},
            "query":{"type":"string","description":"search 时的超理原生查询词；支持 #精品 等论坛搜索语法"},
            "channel":{"type":"string","description":"search 时可选板块，例如 数学/maths/physics；默认 all"},
            "floor":{"type":"integer","minimum":1},
            "radius":{"type":"integer","minimum":0,"maximum":3,"description":"context action 的前后楼层半径；避免与 Agent 内部 context 参数重名"},
            "limit":{"type":"integer","minimum":1,"maximum":30}
        },
        "required":["action"]
    })
    @staticmethod
    def _strict_result(text: str) -> str:
        note = (
            "【严格归属约束】以下信息只能按论坛页面直接绑定关系复述：用户名仅代表论坛账号，不得推断现实身份；"
            "主题作者、最后回复者、楼层作者不可互换；‘引用’内容属于被引用者，不得算作当前楼作者观点；"
            "概括观点时必须保留作者/楼层来源，不确定就明确说无法确认。\n\n"
        )
        return note + str(text or "")

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs) -> ToolExecResult:
        a=str(kwargs.get("action") or ""); target=str(kwargs.get("target") or "").strip()
        async def strict(awaitable):
            return self._strict_result(await awaitable)
        if a=="search": return await strict(ChaoliService.search(str(kwargs.get("query") or target),str(kwargs.get("channel") or "all"),int(kwargs.get("limit",10))))
        if a=="daily":
            await execute_formal_command(context, "/chaoli daily")
            return None
        if a=="daily_push":
            await execute_formal_command(context, "/chaoli daily push")
            return None
        if a=="latest": return await strict(ChaoliService.latest("all",int(kwargs.get("limit",10))))
        if a=="channel": return await strict(ChaoliService.latest(str(kwargs.get("channel") or target or "all"),int(kwargs.get("limit",10))))
        if a=="read": return await strict(ChaoliService.read(target))
        if a=="floor": return await strict(ChaoliService.read(target,int(kwargs.get("floor",1)),0))
        if a=="context": return await strict(ChaoliService.read(target,int(kwargs.get("floor",1)),int(kwargs.get("radius",1))))
        if a=="outline": return await strict(ChaoliService.outline(target,int(kwargs.get("limit",40))))
        if a=="user": return await strict(ChaoliService.user(target,int(kwargs.get("limit",8))))
        if a=="links": return await strict(ChaoliService.links(target,int(kwargs.get("limit",12))))
        if a=="preview": return await strict(ChaoliService.preview(target))
        if a=="status": return await ChaoliService.status()
        raise ValueError("unknown chaoli action")

TOOLS=(DogeMathTool,DogeChemTool,DogeCodecTool,DogeWeatherTool,DogeNasaTool,DogeBingTool,DogeChartTool,DogePaperTool,DogeBioTool,DogeMaterialTool,DogeAstroTool,DogeTrialTool,DogeLookupTool,DogeCthuvianTool,DogePixivTool,DogeChaoliTool)


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
