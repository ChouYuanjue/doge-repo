# Doge Legacy reference

Doge v2-v4 历史功能博物馆。默认 profile 不加载；这里记录旧入口、原用途、退役/迁移状态和仍可追溯的子功能。

- 历史顶层入口：**45**
- 历史叶子功能：**81**
- 默认 profile：**不加载**

这里的‘收容’表示旧功能的用途、入口和迁移状态仍可追溯；`offline` / `broken` / `retired` 等状态不代表当前可以正常执行。

## `/gpt` — v3 GPT-2 continuation

状态：`retired`

当年的小型 GPT-2 文本续写已经被 AstrBot 当前对话模型完全替代；直接和机器人对话即可。

历史叶子：

- `/gpt [历史参数]` — v3 GPT-2 continuation

## `/yg` — v3 AI 约稿/图片生成

状态：`retired`

旧生成后端已过时；现代图片生成应走当前模型/媒体插件，而不是复活旧 API。

历史叶子：

- `/yg [历史参数]` — v3 AI 约稿/图片生成

## `/gan` — v3 StyleGAN 随机猫/人脸/动漫/化学图

状态：`retired`

固定 StyleGAN demo 已失去维护价值；历史子命令 cat/art/horse/waifu/anime/furry/person/chem 仅留档。

历史叶子：

- `/gan cat [历史参数]` — 随机猫
- `/gan art [历史参数]` — 随机艺术图
- `/gan horse [历史参数]` — 随机马
- `/gan waifu [历史参数]` — 随机 waifu
- `/gan anime [历史参数]` — 随机动漫图
- `/gan furry [历史参数]` — 随机 furry
- `/gan person [历史参数]` — 随机人像
- `/gan chem [历史参数]` — 随机化学图

## `/dream` — v3 Google DeepDream

状态：`retired`

算法仍有教学意义，但作为日常图片功能已被现代图像编辑取代；可未来作为 /lab 的视觉实验复刻。

历史叶子：

- `/dream [历史参数]` — v3 Google DeepDream

## `/style` — v3 神经风格迁移

状态：`retired`

旧两图 style-transfer 服务已过时；现代图片编辑能力更强。

历史叶子：

- `/style [历史参数]` — v3 神经风格迁移

## `/toonify` — v3 人像卡通化

状态：`retired`

旧 Toonify 模型链路不再维护；现代图片编辑已覆盖。

历史叶子：

- `/toonify [历史参数]` — v3 人像卡通化

## `/gen` — v3 伪论文生成器

状态：`retired`

math/cs/hep-ph 随机论文生成属于历史玩具，不再作为正式学术能力维护。

历史叶子：

- `/gen math [历史参数]` — 伪数学论文
- `/gen cs [历史参数]` — 伪计算机论文
- `/gen hep-ph [历史参数]` — 伪高能物理论文

## `/siku` — v3 四库全书检索/阅读

状态：`offline`

旧 siku/skqs 上游已失效。功能目的保留，若找到稳定数字人文接口可在独立插件重新实现。

历史叶子：

- `/siku search [历史参数]` — 四库检索
- `/siku read [历史参数]` — 四库正文阅读

## `/perc` — v3 Perchance generator bridge

状态：`offline`

旧 Glitch 转发桥已返回 410；不再依赖该脆弱链路。

历史叶子：

- `/perc [历史参数]` — v3 Perchance generator bridge

## `/phil` — v3 哲学语录/关键词

状态：`offline`

旧 philosophyapi 后端不可达；作为历史入口保留。

历史叶子：

- `/phil quote [历史参数]` — 哲学语录
- `/phil keyword [历史参数]` — 哲学关键词

## `/poem` — v3 随机诗词

状态：`archived`

原功能属于轻娱乐，后续若恢复应进入独立文化/文本插件，而不是 core。

历史叶子：

- `/poem [历史参数]` — v3 随机诗词

## `/insult` — v3 文化人骂街

状态：`archived`

原模板/语料玩法保留历史记录，不作为默认功能。

历史叶子：

- `/insult [历史参数]` — v3 文化人骂街

## `/fru` — v3 假俄语转换

状态：`archived`

原 en/py/zh 转换玩法可恢复，但低频，暂仅保留语义。

历史叶子：

- `/fru en [历史参数]` — 英语假俄语化
- `/fru py [历史参数]` — 拼音假俄语化
- `/fru zh [历史参数]` — 中文假俄语化

## `/rua` — v3 图片表情变形

状态：`archived`

旧图片模板链路留档；正式图片玩法将统一进入 media。

历史叶子：

- `/rua [历史参数]` — v3 图片表情变形

## `/jeffjoke` — v3 Jeff 笑话生成

状态：`archived`

历史模板生成器；原 mj/myjoke/dj/diyjoke 语义保留。

历史叶子：

- `/jeffjoke mj [历史参数]` — 模板笑话
- `/jeffjoke myjoke [历史参数]` — 自定义笑话
- `/jeffjoke dj [历史参数]` — 段子
- `/jeffjoke diyjoke [历史参数]` — DIY 笑话

## `/px` — v3 Pixiv 搜索/搜图/setu

状态：`retired`

旧 Pixiv 非官方接口与内容策略均不适合作为默认能力；历史 id/user/tst/tsf/setu/kw 留档。

历史叶子：

- `/px id [历史参数]` — Pixiv 作品 ID
- `/px user [历史参数]` — Pixiv 用户
- `/px tst [历史参数]` — 以图搜图
- `/px tsf [历史参数]` — 图片检索
- `/px setu [历史参数]` — 随机图
- `/px kw [历史参数]` — 关键词检索

## `/yan` — v3 群友‘圣训’语料统计

状态：`retired`

旧实现涉及被动收集群友语料，隐私模型不再适合；不会默认恢复。

历史叶子：

- `/yan [历史参数]` — v3 群友‘圣训’语料统计

## `/se` — v3 被主动封印的 secret 功能

状态：`sealed`

原作者当时就标记为封印；其中部分行为不适合现代 bot，保持封印。

历史叶子：

- `/se [历史参数]` — v3 被主动封印的 secret 功能

## `/genshin` — v3/v4 原神抽卡

状态：`offline`

旧卡池/接口/数据年代久远，且 v4 API key 配置无效；不伪装成当前游戏数据。

历史叶子：

- `/genshin [历史参数]` — v3/v4 原神抽卡

## `/honkai` — v4 崩坏查询

状态：`broken`

旧实现存在未定义 session/Path/uuid 且依赖失效配置，保留故障说明。

历史叶子：

- `/honkai [历史参数]` — v4 崩坏查询

## `/pack` — v4 Magdeburg packing CGI

状态：`offline`

旧 CGI 后端实测超时；功能概念可未来在 /lab 以本地算法重做。

历史叶子：

- `/pack [历史参数]` — v4 Magdeburg packing CGI

## `/doubao` — v4 豆包模型专用入口

状态：`retired`

模型品牌专用命令已被 AstrBot provider 抽象取代；直接使用当前 provider。

历史叶子：

- `/doubao [历史参数]` — v4 豆包模型专用入口

## `/lcha` — v4 LiblibAI 查任务

状态：`archived`

旧 LiblibAI 专用 API 工具留档，不进入默认功能。

历史叶子：

- `/lcha [历史参数]` — v4 LiblibAI 查任务

## `/ltran` — v4 LiblibAI 文生图

状态：`retired`

固定平台文生图接口已被通用图片生成工作流取代。

历史叶子：

- `/ltran [历史参数]` — v4 LiblibAI 文生图

## `/lsd` — v4 LiblibAI SD

状态：`retired`

历史 Stable Diffusion 平台调用入口留档。

历史叶子：

- `/lsd [历史参数]` — v4 LiblibAI SD

## `/lflux` — v4 LiblibAI Flux

状态：`retired`

历史平台模型入口留档；不把具体模型名固化成长期指令。

历史叶子：

- `/lflux [历史参数]` — v4 LiblibAI Flux

## `/lcon` — v4 LiblibAI ControlNet

状态：`retired`

历史平台专用控制图入口留档。

历史叶子：

- `/lcon [历史参数]` — v4 LiblibAI ControlNet

## `/limg` — v4 LiblibAI 图生图

状态：`retired`

历史平台专用图生图入口留档。

历史叶子：

- `/limg [历史参数]` — v4 LiblibAI 图生图

## `/amuse` — v3 零乱娱乐功能

状态：`archived`

旧 chp/zuan/du/gar/tian/cp 等群聊娱乐玩法统一留档；不再把低质量外部文案 API 放回正式模块。

历史叶子：

- `/amuse chp [历史参数]` — 彩虹屁
- `/amuse zuan [历史参数]` — 嘴臭文案
- `/amuse du [历史参数]` — 毒鸡汤
- `/amuse gar [历史参数]` — 尬聊文案
- `/amuse tian [历史参数]` — 舔狗日记
- `/amuse cp [历史参数]` — CP 文案

## `/netool` — v3 ping/web/nmap/gc 网络工具

状态：`retired`

旧实现允许用户驱动宿主网络探测，不适合现代公共群机器人；如需网络诊断应使用受控 Agent/运维工具。

历史叶子：

- `/netool ping [历史参数]` — Ping
- `/netool web [历史参数]` — 网页探测
- `/netool nmap [历史参数]` — 端口探测
- `/netool gc [历史参数]` — 网络小工具

## `/chart` — v3/v4 Chart.js / QuickChart

状态：`migrated`

原始 Chart.js JSON 入口已由正式 /diagram vegalite 取代；旧 QuickChart 语义仅留档。

历史叶子：

- `/chart [历史参数]` — v3/v4 Chart.js / QuickChart

## `/api` — v4 可配置 API 管理器

状态：`retired`

旧插件把任意 HTTP API 配置直接暴露为群指令，边界与密钥管理都较弱；现代能力改由各正式 domain service/Agent Tool 管理。

历史叶子：

- `/api [历史参数]` — v4 可配置 API 管理器

## `/emojimix` — v4 emoji 合成

状态：`archived`

历史 Emoji Kitchen 风格入口留档；若恢复应进入独立 memes/media 域并复用当前稳定上游。

历史叶子：

- `/emojimix [历史参数]` — v4 emoji 合成

## `/meme` — v3/v4 表情包与模板管理

状态：`archived`

旧模板系统与资源仍有参考价值，但当前正式媒体模块尚未完成；先完整保留历史语义。

历史叶子：

- `/meme [历史参数]` — v3/v4 表情包与模板管理

## `/mirage` — v3/v4 幻影坦克图片

状态：`migrated`

历史图片合成玩法已经现代化为正式 `/media mirage gray|color`，使用本地 Pillow/NumPy 实现。

历史叶子：

- `/mirage [历史参数]` — v3/v4 幻影坦克图片

## `/music` — v4 点歌/音乐搜索

状态：`archived`

旧非官方音乐接口较脆弱；正式 music 域只会在找到稳定上游后恢复。

历史叶子：

- `/music [历史参数]` — v4 点歌/音乐搜索

## `/lyrics` — v4 歌词搜索

状态：`archived`

旧歌词链路与 music 同属历史媒体能力，暂不依赖非官方接口。

历史叶子：

- `/lyrics [历史参数]` — v4 歌词搜索

## `/vv` — v4 视频/媒体辅助

状态：`archived`

旧 vvapi 入口留档；后续统一并入 media 编排，不单独维持顶层命令。

历史叶子：

- `/vv [历史参数]` — v4 视频/媒体辅助

## `/trace` — v4 trace.moe / 动漫图片识别

状态：`migrated`

动漫/Gal 图片识别已经迁入正式 `/media trace anime|gal`，当前使用 AnimeTrace 并保留真实后端失败说明。

历史叶子：

- `/trace [历史参数]` — v4 trace.moe / 动漫图片识别

## `/st` — v4 图片搜索/识别辅助

状态：`archived`

旧图片检索入口留档；正式恢复应复用当前成熟 image-exploration 插件。

历史叶子：

- `/st [历史参数]` — v4 图片搜索/识别辅助

## `/mc` — v4 Minecraft 查询/服务器管理

状态：`archived`

旧 mclist/mcget/mcadd/mcdel/mcup 等语义留档；只有在确定真实使用场景后才恢复独立模块。

历史叶子：

- `/mc mclist [历史参数]` — 服务器列表
- `/mc mcget [历史参数]` — 服务器查询
- `/mc mcadd [历史参数]` — 添加服务器
- `/mc mcdel [历史参数]` — 删除服务器
- `/mc mcup [历史参数]` — 更新服务器

## `/law` — v2/v3 法律片段/今日刑法

状态：`offline`

旧网页抓取源年代久远且不适合做可靠法律信息源；历史用途保留，不提供法律判断。

历史叶子：

- `/law [历史参数]` — v2/v3 法律片段/今日刑法

## `/anime` — v2 随机动漫/图片内容

状态：`retired`

旧随机媒体接口和内容源已过时；现代媒体能力不复活这一随机接口。

历史叶子：

- `/anime [历史参数]` — v2 随机动漫/图片内容

## `/say` — v2 say/TTS 风格入口

状态：`archived`

旧第三方语音/复读实现留档；若恢复应基于当前平台原生语音能力。

历史叶子：

- `/say [历史参数]` — v2 say/TTS 风格入口

## `/arknights` — v2 明日方舟寻访/库存/保底状态机

状态：`archived`

完整用户语义已收容；几十条 EPK 变量/库存/保底节点属于内部状态机，不逐条注册成假功能。

历史叶子：

- `/arknights draw [历史参数]` — 寻访
- `/arknights inventory [历史参数]` — 库存
- `/arknights up [历史参数]` — UP/卡池
- `/arknights status [历史参数]` — 保底与每日状态
