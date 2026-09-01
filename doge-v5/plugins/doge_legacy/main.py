from __future__ import annotations

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.presentation import long_result, text_result
from data.plugins.doge_shared.raw_command import command_payload

# Historical commands that are intentionally not part of the modern default
# surface.  The legacy plugin is a museum: preserving names, intent, and a
# useful failure/migration explanation is more important than pretending an
# obsolete backend still works.
HISTORY = {
    "gpt": ("v3 GPT-2 continuation", "retired", "当年的小型 GPT-2 文本续写已经被 AstrBot 当前对话模型完全替代；直接和机器人对话即可。"),
    "yg": ("v3 AI 约稿/图片生成", "retired", "旧生成后端已过时；现代图片生成应走当前模型/媒体插件，而不是复活旧 API。"),
    "gan": ("v3 StyleGAN 随机猫/人脸/动漫/化学图", "retired", "固定 StyleGAN demo 已失去维护价值；历史子命令 cat/art/horse/waifu/anime/furry/person/chem 仅留档。"),
    "dream": ("v3 Google DeepDream", "retired", "算法仍有教学意义，但作为日常图片功能已被现代图像编辑取代；可未来作为 /lab 的视觉实验复刻。"),
    "style": ("v3 神经风格迁移", "retired", "旧两图 style-transfer 服务已过时；现代图片编辑能力更强。"),
    "toonify": ("v3 人像卡通化", "retired", "旧 Toonify 模型链路不再维护；现代图片编辑已覆盖。"),
    "gen": ("v3 伪论文生成器", "retired", "math/cs/hep-ph 随机论文生成属于历史玩具，不再作为正式学术能力维护。"),
    "siku": ("v3 四库全书检索/阅读", "offline", "旧 siku/skqs 上游已失效。功能目的保留，若找到稳定数字人文接口可在独立插件重新实现。"),
    "perc": ("v3 Perchance generator bridge", "offline", "旧 Glitch 转发桥已返回 410；不再依赖该脆弱链路。"),
    "phil": ("v3 哲学语录/关键词", "offline", "旧 philosophyapi 后端不可达；作为历史入口保留。"),
    "poem": ("v3 随机诗词", "archived", "原功能属于轻娱乐，后续若恢复应进入独立文化/文本插件，而不是 core。"),
    "insult": ("v3 文化人骂街", "archived", "原模板/语料玩法保留历史记录，不作为默认功能。"),
    "fru": ("v3 假俄语转换", "archived", "原 en/py/zh 转换玩法可恢复，但低频，暂仅保留语义。"),
    "rua": ("v3 图片表情变形", "archived", "旧图片模板链路留档；正式图片玩法将统一进入 media。"),
    "jeffjoke": ("v3 Jeff 笑话生成", "archived", "历史模板生成器；原 mj/myjoke/dj/diyjoke 语义保留。"),
    "px": ("v3 Pixiv 搜索/搜图/setu", "retired", "旧 Pixiv 非官方接口与内容策略均不适合作为默认能力；历史 id/user/tst/tsf/setu/kw 留档。"),
    "yan": ("v3 群友‘圣训’语料统计", "retired", "旧实现涉及被动收集群友语料，隐私模型不再适合；不会默认恢复。"),
    "se": ("v3 被主动封印的 secret 功能", "sealed", "原作者当时就标记为封印；其中部分行为不适合现代 bot，保持封印。"),
    "genshin": ("v3/v4 原神抽卡", "offline", "旧卡池/接口/数据年代久远，且 v4 API key 配置无效；不伪装成当前游戏数据。"),
    "honkai": ("v4 崩坏查询", "broken", "旧实现存在未定义 session/Path/uuid 且依赖失效配置，保留故障说明。"),
    "pack": ("v4 Magdeburg packing CGI", "offline", "旧 CGI 后端实测超时；功能概念可未来在 /lab 以本地算法重做。"),
    "doubao": ("v4 豆包模型专用入口", "retired", "模型品牌专用命令已被 AstrBot provider 抽象取代；直接使用当前 provider。"),
    "lcha": ("v4 LiblibAI 查任务", "archived", "旧 LiblibAI 专用 API 工具留档，不进入默认功能。"),
    "ltran": ("v4 LiblibAI 文生图", "retired", "固定平台文生图接口已被通用图片生成工作流取代。"),
    "lsd": ("v4 LiblibAI SD", "retired", "历史 Stable Diffusion 平台调用入口留档。"),
    "lflux": ("v4 LiblibAI Flux", "retired", "历史平台模型入口留档；不把具体模型名固化成长期指令。"),
    "lcon": ("v4 LiblibAI ControlNet", "retired", "历史平台专用控制图入口留档。"),
    "limg": ("v4 LiblibAI 图生图", "retired", "历史平台专用图生图入口留档。"),
    "amuse": ("v3 零乱娱乐功能", "archived", "旧 chp/zuan/du/gar/tian/cp 等群聊娱乐玩法统一留档；不再把低质量外部文案 API 放回正式模块。"),
    "netool": ("v3 ping/web/nmap/gc 网络工具", "retired", "旧实现允许用户驱动宿主网络探测，不适合现代公共群机器人；如需网络诊断应使用受控 Agent/运维工具。"),
    "chart": ("v3/v4 Chart.js / QuickChart", "migrated", "原始 Chart.js JSON 入口已由正式 /diagram vegalite 取代；旧 QuickChart 语义仅留档。"),
    "api": ("v4 可配置 API 管理器", "retired", "旧插件把任意 HTTP API 配置直接暴露为群指令，边界与密钥管理都较弱；现代能力改由各正式 domain service/Agent Tool 管理。"),
    "emojimix": ("v4 emoji 合成", "archived", "历史 Emoji Kitchen 风格入口留档；若恢复应进入独立 memes/media 域并复用当前稳定上游。"),
    "meme": ("v3/v4 表情包与模板管理", "archived", "旧模板系统与资源仍有参考价值，但当前正式媒体模块尚未完成；先完整保留历史语义。"),
    "mirage": ("v3/v4 幻影坦克图片", "archived", "旧图片合成玩法留档；未来若恢复应进入 memes/media，而不是 core。"),
    "music": ("v4 点歌/音乐搜索", "archived", "旧非官方音乐接口较脆弱；正式 music 域只会在找到稳定上游后恢复。"),
    "lyrics": ("v4 歌词搜索", "archived", "旧歌词链路与 music 同属历史媒体能力，暂不依赖非官方接口。"),
    "vv": ("v4 视频/媒体辅助", "archived", "旧 vvapi 入口留档；后续统一并入 media 编排，不单独维持顶层命令。"),
    "trace": ("v4 trace.moe / 动漫图片识别", "archived", "能力本身仍有价值，但应由现代 media/image-exploration 域复用成熟插件，而不是继续维护旧单点实现。"),
    "st": ("v4 图片搜索/识别辅助", "archived", "旧图片检索入口留档；正式恢复应复用当前成熟 image-exploration 插件。"),
    "mc": ("v4 Minecraft 查询/服务器管理", "archived", "旧 mclist/mcget/mcadd/mcdel/mcup 等语义留档；只有在确定真实使用场景后才恢复独立模块。"),
    "law": ("v2/v3 法律片段/今日刑法", "offline", "旧网页抓取源年代久远且不适合做可靠法律信息源；历史用途保留，不提供法律判断。"),
    "anime": ("v2 随机动漫/图片内容", "retired", "旧随机媒体接口和内容源已过时；现代媒体能力不复活这一随机接口。"),
    "say": ("v2 say/TTS 风格入口", "archived", "旧第三方语音/复读实现留档；若恢复应基于当前平台原生语音能力。"),
    "arknights": ("v2 明日方舟寻访/库存/保底状态机", "archived", "完整用户语义已收容；几十条 EPK 变量/库存/保底节点属于内部状态机，不逐条注册成假功能。"),
}


@register("doge_legacy", "runnel", "Doge v2-v4 历史功能博物馆（默认不启用）", "5.4.0")
class DogeLegacy(Star):
    def __init__(self, context: Context):
        super().__init__(context)

    def _message(self, command: str, payload: str = "") -> str:
        title, state, note = HISTORY[command]
        original = f"\n原输入：`/{command} {payload}`" if payload.strip() else ""
        return f"**/{command} · {title}**\n\n状态：`{state}`\n\n{note}{original}"

    async def _show(self, event: AstrMessageEvent, command: str):
        yield text_result(event, self._message(command, command_payload(event.message_str, command)))

    @filter.command("legacy")
    async def legacy(self, event: AstrMessageEvent):
        body = "\n".join(f"- `/{k}` — {v[0]} · `{v[1]}`" for k, v in HISTORY.items())
        yield long_result(event, "Doge Legacy Museum", body, fold_threshold=1200)

    @filter.command("gpt")
    async def gpt(self,event):
        async for x in self._show(event,"gpt"): yield x
    @filter.command("yg")
    async def yg(self,event):
        async for x in self._show(event,"yg"): yield x
    @filter.command("gan")
    async def gan(self,event):
        async for x in self._show(event,"gan"): yield x
    @filter.command("dream")
    async def dream(self,event):
        async for x in self._show(event,"dream"): yield x
    @filter.command("style")
    async def style(self,event):
        async for x in self._show(event,"style"): yield x
    @filter.command("toonify")
    async def toonify(self,event):
        async for x in self._show(event,"toonify"): yield x
    @filter.command("gen")
    async def gen(self,event):
        async for x in self._show(event,"gen"): yield x
    @filter.command("siku")
    async def siku(self,event):
        async for x in self._show(event,"siku"): yield x
    @filter.command("perc")
    async def perc(self,event):
        async for x in self._show(event,"perc"): yield x
    @filter.command("phil")
    async def phil(self,event):
        async for x in self._show(event,"phil"): yield x
    @filter.command("poem")
    async def poem(self,event):
        async for x in self._show(event,"poem"): yield x
    @filter.command("insult")
    async def insult(self,event):
        async for x in self._show(event,"insult"): yield x
    @filter.command("fru")
    async def fru(self,event):
        async for x in self._show(event,"fru"): yield x
    @filter.command("rua")
    async def rua(self,event):
        async for x in self._show(event,"rua"): yield x
    @filter.command("jeffjoke")
    async def jeffjoke(self,event):
        async for x in self._show(event,"jeffjoke"): yield x
    @filter.command("px")
    async def px(self,event):
        async for x in self._show(event,"px"): yield x
    @filter.command("yan")
    async def yan(self,event):
        async for x in self._show(event,"yan"): yield x
    @filter.command("se")
    async def se(self,event):
        async for x in self._show(event,"se"): yield x
    @filter.command("genshin")
    async def genshin(self,event):
        async for x in self._show(event,"genshin"): yield x
    @filter.command("honkai")
    async def honkai(self,event):
        async for x in self._show(event,"honkai"): yield x
    @filter.command("pack")
    async def pack(self,event):
        async for x in self._show(event,"pack"): yield x
    @filter.command("doubao")
    async def doubao(self,event):
        async for x in self._show(event,"doubao"): yield x
    @filter.command("lcha")
    async def lcha(self,event):
        async for x in self._show(event,"lcha"): yield x
    @filter.command("ltran")
    async def ltran(self,event):
        async for x in self._show(event,"ltran"): yield x
    @filter.command("lsd")
    async def lsd(self,event):
        async for x in self._show(event,"lsd"): yield x
    @filter.command("lflux")
    async def lflux(self,event):
        async for x in self._show(event,"lflux"): yield x
    @filter.command("lcon")
    async def lcon(self,event):
        async for x in self._show(event,"lcon"): yield x
    @filter.command("limg")
    async def limg(self,event):
        async for x in self._show(event,"limg"): yield x
    @filter.command("amuse")
    async def amuse(self,event):
        async for x in self._show(event,"amuse"): yield x
    @filter.command("netool")
    async def netool(self,event):
        async for x in self._show(event,"netool"): yield x
    @filter.command("chart")
    async def chart(self,event):
        async for x in self._show(event,"chart"): yield x
    @filter.command("api")
    async def api(self,event):
        async for x in self._show(event,"api"): yield x
    @filter.command("emojimix")
    async def emojimix(self,event):
        async for x in self._show(event,"emojimix"): yield x
    @filter.command("meme")
    async def meme(self,event):
        async for x in self._show(event,"meme"): yield x
    @filter.command("mirage")
    async def mirage(self,event):
        async for x in self._show(event,"mirage"): yield x
    @filter.command("music")
    async def music(self,event):
        async for x in self._show(event,"music"): yield x
    @filter.command("lyrics")
    async def lyrics(self,event):
        async for x in self._show(event,"lyrics"): yield x
    @filter.command("vv")
    async def vv(self,event):
        async for x in self._show(event,"vv"): yield x
    @filter.command("trace")
    async def trace(self,event):
        async for x in self._show(event,"trace"): yield x
    @filter.command("st")
    async def st(self,event):
        async for x in self._show(event,"st"): yield x
    @filter.command("mc")
    async def mc(self,event):
        async for x in self._show(event,"mc"): yield x
    @filter.command("law")
    async def law(self,event):
        async for x in self._show(event,"law"): yield x
    @filter.command("anime")
    async def anime(self,event):
        async for x in self._show(event,"anime"): yield x
    @filter.command("say")
    async def say(self,event):
        async for x in self._show(event,"say"): yield x
    @filter.command("arknights")
    async def arknights(self,event):
        async for x in self._show(event,"arknights"): yield x
