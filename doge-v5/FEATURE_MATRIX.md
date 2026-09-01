# v2-v4 → v5 功能迁移矩阵

按“用户为什么会调用它”而不是历史目录名归并。`reuse` 表示直接链接/复制旧 AstrBot 插件；`native-restore` 表示旧代码生态不能直接运行但功能仍值得以小型 Python service 恢复。

| v5 功能 | 历史来源 | 决策 | Agent | 说明 |
|---|---|---|---|---|
| `apis` | v4/apis | rework | later | 保留统一入口的价值，但当前允许任意 URL 且删除配置无权限保护，存在 SSRF/误删风险；还有 data.plugins 硬编码导入。 |
| `math` | v2/random/pi/logic、v3/math、v3/wa、v4/wa | native+reuse | yes | 本地计算可无依赖实现；pi.delivery/OEIS/WolframAlpha 仍可用。将 /wa 保留为兼容后端而不是独立产品概念。 |
| `chem` | v3/chem | native | yes | NCI Cactus 当前仍稳定可访问，功能小而有明确学术价值。 |
| `tex` | v3/tex、v4/latex、v4/utex | native-v5 | yes | 统一 raw payload；默认原生 TeX（align/matrix/TikZ），本地 MathText 作隐私/断网 fallback；不再部署旧 latex/utex。 |
| `typst` | v4/typst | native-v5 | yes | typst-py 0.15；math/card/doc/chat、多页 PNG、CJK font_paths 与清晰错误；不再部署旧 doge_typst。 |
| `chart` | v3/chart | native | yes | QuickChart 仍可用；与 Mermaid 的流程图/关系图用途不同。 |
| `mermaid` | v4/mermaid | reuse | yes | 现实现成熟且已经接入 LLM Tool，直接复用。 |
| `complex` | v4/complex | optional | later | 价值明确，但依赖浏览器/Selenium/Playwright 和第三方网页，运行成本及脆弱性较高，默认不启用。 |
| `fourier` | v4/fourier | reuse | yes | 本地计算为主，依赖可控。 |
| `lab` | v4/fourier、new Scientific Playground | native-v5 | no | NumPy/Pillow 本地科学可视化与小实验；优先直观、可参数化和群聊缩略图可读，CPU 图像生成不默认暴露给 Agent。 |
| `circuit` | new/Schemdraw | optional-wrapper | no | 用短 DSL 薄封装 Schemdraw；重依赖惰性导入。 |
| `control` | new/python-control | optional-wrapper | no | 直接复用标准 Bode/Nyquist/root-locus/step/impulse 计算；SciPy/Matplotlib 按需安装。 |
| `crystal` | new/Dans_Diffraction | optional-wrapper | no | `/lab xrd` 只做教学选择定则；真实 CIF/mCIF 的晶胞与 powder XRD 走 Dans_Diffraction。 |
| `run` | v3/run、v4/run | reuse-then-sandbox | no-direct | 菜鸟教程当前实测 print(1) 可执行；保留兼容指令，但 Agent 执行代码长期切 AstrBot Sandbox。 |
| `aigen` | v3/yg、v3/gpt、v3/dream、v3/style、v3/toonify、v3/gan、v4/doubao、v4/liblibapi | merge+reuse | yes | 旧 DeepAI/GAN 专项入口已被现代多模态模型覆盖；统一为 aigen，底层先复用 doubao/liblibapi 和旧别名。 |
| `trace` | v2/以图搜番/瓶、v3/px search、v4/trace | merge+reuse | yes | 保留“识图找来源”的目的；AnimeTrace、trace.moe/SauceNAO 都有可用路径，删除直接 Pixiv 抓取和 R18/setu。 |
| `st` | v4/st | reuse | yes | Safebooru DAPI 当前可用，定位比旧随机图接口更清晰。 |
| `music` | v4/music、v4/lyrics | merge+reuse | yes | 用户目的高度相同；实现先保持两个插件。网易云/酷狗当前仍可访问，QQ 音乐接口需继续防脆弱。 |
| `meme` | v3/rua、v3/meme、v4/meme、v4/vv | merge+reuse | yes | 旧 rua 与固定图包被现代 meme_generator 覆盖；vv 作为搜索后端保留在同一功能域。 |
| `emojimix` | v4/emojimix | reuse | yes | 自动触发行为独特，不与 meme 强行合并。 |
| `mirage` | v3/mirage、v4/mirage | reuse | yes | v4 已有纯 Python/Pillow 实现。 |
| `pokemon` | v4/pokemon | reuse | yes | FusionCalc/GitLab 数据源当前实测可访问。 |
| `mihoyo` | v3/genshin gacha、v4/genshin、v4/honkai | rework | yes-after-fix | 攻略目的可合并，但当前两个 v4 插件都写死 your-key；honkai 还引用未定义 session/Path/uuid。旧原神抽卡不恢复。 |
| `nasa` | v3/mirai-jvm/nasa | native-restore | yes | v3 源码存在但非 Python；NASA 官方 API 当前仍可用，适合小型 Python service 恢复。 |
| `bing` | v3/bing | native-restore | yes | Bing HPImageArchive 当前可访问；旧功能小而稳定。 |
| `mc` | v4/mc | reuse | yes | 现实现完整，mcstatus 仍维护。 |
| `wiki` | v3/repo、v4/wiki | reuse | yes | DeepWiki/Devin API 入口仍在线；尤其适合 Agent 工具。 |
| `tangut` | v4/tangut | reuse | yes | 本地数据驱动，领域特色明显。 |
| `rrpl` | v4/rrpl | rework | yes-after-fix | 当前写死 /root/AstrBot/data/plugins/rrpl/rrpl，且依赖 Node/fontforge；先修路径再启用。 |
| `cotool` | v3/cotool | native-restore | yes | 完全可本地实现；旧加密格式不明确且不应自创密码学，encrypt/decrypt 不恢复。 |
| `amuse` | v2/夸骂毒舔/乱码、v3/amuse、v3/insult、v3/jeffjoke、v3/fru、v3/poem、v3/phil | trim | later | 保留适合本地实现且有辨识度的 fru/jeffjoke；夸骂诗歌哲学无需再依赖碎片 API，可交给 LLM；旧 philosophy API 已不可用。 |
| `fuse` | new/alchemy | native-v5 | no | 群共享概念炼金与发现图鉴；同一配方稳定复现，结果可继续作为素材。 |
| `signal` | new/signal | native-v5 | no | 程序化多层可逆编码解密接力，不依赖固定谜题库。 |
| `shock` | v2/给我光明/电疗 | native-restore | no | v2 很有辨识度且依赖 NapCat/OneBot 原生群禁言；只允许禁言自己，不暴露为 Agent Tool。 |
| `cube` | v4/cube | reuse | no | 现实现本地化且成熟。 |
| `gol` | v4/gol | reuse | yes | 本地化、无外部服务依赖。 |
| `gomoku` | v4/gomoku | reuse | no | 状态型游戏，现实现完整。 |
| `poker` | v4/poker | reuse | no | 状态型游戏，现实现完整；不应交给 Agent 自主下注。 |
| `wordle` | v4/wordle | reuse | no | 本地状态型游戏。 |
| `game` | v3/game 24p、nine chess | native-v5 | no | 旧 Kotlin/Java 已 Python 重写；24 点用 Fraction 精确求解/校验，九子棋补齐磨坊吃子、移动和三子飞行的标准规则。 |
| `soup` | v4/soup | reuse | internal | 已经天然是 LLM 驱动会话型游戏，继续作为独立应用而不是普通工具。 |
| `pjsk` | v4/pjsk | optional-reuse | no | 功能完整但资源与依赖较重，默认按需部署。 |
| `arena` | v4/wp、new/arena | native-v5 | no | v4 `/wp` 238 条手写弱能力与直接对决语义完整保留；`draw/fight` 为原味路径，`duel/chaos` 只叠加场景和组合条款，能力卡组合空间 >3727 亿。 |

## 删除或仅归档

| 历史功能 | 处理理由 |
|---|---|
| v3/siku | siku.guoxuedashi.net 与 skqs.guoxuedashi.net 当前 DNS 失效；不为了复刻而换一套来源。 |
| v3/perc | 自建 Glitch bridge 当前 HTTP 410；Perchance 本身无稳定官方 API。 |
| v3/netool (web/nmap/gfw) | 公共聊天机器人暴露扫描/任意网页请求收益低、SSRF/滥用面大；Agent 如需网络能力应走受控 Web/MCP。 |
| v3/px 直接 Pixiv/keyword/setu | 接口和代理链陈旧，且内容治理/封号风险高；只保留 trace 的识图找来源目的。 |
| v3/yan | 无差别语录记录有隐私与同意成本；除非未来做显式 opt-in，不默认恢复。 |
| v3/se | 原文已封印且主要是成人/挑衅性入口，无恢复价值。 |
| v2 明日方舟寻访 | 大量规则只是旧卡池状态机，维护成本高且数据语义过时。 |
| v2 随机老婆/猫娘/狗粮/旧本地梗图 | 依赖已失效随机图 API 或缺失素材；由 st/meme/aigen 覆盖用户目的。 |
| v3 gen(Mathgen/Scigen) | 趣味性可由 Agent/LLM 直接生成，不值得保留网页截图式专用依赖。 |
| v4/pack | Magdeburg hydra CGI 从服务器实测超时；暂不为它重写圆堆积求解器。 |
| v4/ise（仅文档） | v4_docs 有条目但仓库没有对应源码目录，无法诚实迁移；等找到源文件再评估。 |

## 实测可行性记录（2026-08-31，alibaba-server-10）

- 可访问：upmath、AnimeTrace、WolframAlpha API（缺 appid 时正确报错）、DeepWiki、Safebooru、FusionCalc/InfiniteFusion GitLab、网易云搜索、酷狗、NCI Cactus、pi.delivery、OEIS、NASA APOD、Bing HPImageArchive。
- `run` 的菜鸟教程实现实际抓到 token，并执行 `print(1)` 得到 `1`。
- `genshin/honkai` 的 yaohud 域名仍响应，但 v4 源码写死 `your-key`；`honkai` 另有未定义对象，必须重构。
- `pack` 的 Magdeburg CGI 实测超时；四库全书旧域名 DNS 失败；旧 Perchance Glitch bridge 返回 HTTP 410。
- v4 全目录可通过 Python 3.11 `compileall`，但只能证明语法成立，不能覆盖上述运行时问题。

## v2 的处理原则

v2 的 108 条 EPK 规则中，大量条目其实是同一功能的内部状态节点（尤其明日方舟寻访）、插件胶水或私有梗回复，不能按 108 个“功能”迁移。v5 只恢复真正独立的用户目的：自助禁言并入 `shock`，数学/随机/π 并入 `math`，识图并入 `trace`，轻娱乐并入 `amuse`。群成员进出提示可以做平台事件配置项，但不再当核心功能块。

## 依赖层可行性

v4 各目录没有独立 `requirements.txt`，过去依赖仓库根目录的一份超大 requirements。直接复用源码不等于应继续把那份旧锁文件整体装进 v5。当前 AstrBot 4.27.x 本身已提供 aiohttp、httpx、Pillow、pydub、qrcode、pandas/pydantic 等常用运行库；其余能力应按功能补增量依赖。旧总依赖中可见的典型额外项包括 `matplotlib`、`scipy`、`opencv-python`、`CairoSVG`、`mcstatus`、`meme_generator`、`playwright`、`selenium`、`moviepy`、`fonttools`。其中浏览器类依赖对应的 `complex` 已设为 optional，资源/凭据较重的 `music`、`aigen`、`pjsk` 同样不默认物化。v5 的物化器只管理源码位置，**不会静默安装系统包或启动浏览器**。
