# 豆子 Doge

![GitHub repo size](https://img.shields.io/github/repo-size/ChouYuanjue/doge-repo)
![GitHub last commit](https://img.shields.io/github/last-commit/ChouYuanjue/doge-repo)
![GitHub stars](https://img.shields.io/github/stars/ChouYuanjue/doge-repo)

> 从 2019 年延续至今的 QQ 群聊机器人。当前主线是 **Doge v5 / AstrBot**；v2-v4 作为可追溯历史保留。

Doge 不是一个只会聊天的单一模型壳。v5 把旧版本长期积累的功能重构为一组可独立维护的 AstrBot 插件，并在它们之上提供统一的 Agent 编排层：普通用户既可以使用明确的 `/command` 获得原始、可重复的工具结果，也可以直接自然语言询问，由 Agent 选择并组合多个正式能力。

当前能力与命令的**唯一权威来源**是 `doge-v5/plugins/doge_shared/resources/capability_registry.json`。仓库中的 `doge-v5/HELP.md` 由它自动生成；运行时 `/help`、使用统计和 Agent capability inventory 也读取同一份 registry。

## 当前版本：Doge v5

Doge v5 面向 **AstrBot 4.27.x / Python 3.12**，目前生产同时服务 QQ Official 与 NapCat/OneBot。正式能力默认全部加载，Legacy 历史插件默认关闭。

主要能力包括：

- **检索与科研数据**：论文、PubMed/arXiv、UniProt、InterPro、PDB、AlphaFold、PubChem、ChEMBL、OPTIMADE、SIMBAD、NASA Exoplanet、ClinicalTrials.gov 等；
- **数学 / CS / AI**：基础与高精度数值、SymPy 符号代数/微积分、数论、统计、π、OEIS、Wolfram|Alpha、Lean/Coq(Rocq)/Rzk 轻量形式化入口，以及自动机、PageRank、micrograd、minBPE、远端受限代码执行；
- **排版与图形**：TeX、Typst、Markdown 卡片/PDF、代码片段、Graphviz、Mermaid、Vega-Lite；
- **科学与工程实验**：分形、混沌、生命游戏 GIF/元胞自动机、随机矩阵、量子/相对论教学图、晶格/XRD、电路、控制系统等；这里强调可视化、模拟和直觉，而 `/math` 负责精确/符号求解；
- **语言学**：西夏文双向词典 grounding 翻译、GX/GHC 拟音、汉字历史音系/方言、带 `syntax/explain/render` 指引的 RRPL、R'lyehian/Cthuvian；
- **群聊游戏与原生玩法**：24 点、九子棋、Signal、扫雷、数独、骰池、概念炼金，以及完整保留原 `/wp` 238 条弱能力的 Arena；
- **媒体工具**：AnimeTrace、Galgame 识图、本地幻影坦克等；
- **运行与管理**：版本、状态、统计、分层 Help，以及按群隔离的正式模块开关。

完整命令表见 [`doge-v5/HELP.md`](doge-v5/HELP.md)。历史能力与迁移状态见 [`doge-v5/LEGACY.md`](doge-v5/LEGACY.md)。

## Agent 与直接命令

v5 有两种等价但用途不同的入口。

**直接命令**适合需要完整原始输出、可重复调用或精确参数控制的场景，例如：

```text
/math solve x^2-5*x+6=0 --var x
/math oeis 1,1,2,3,5,8
/lang tangut zh2t 我爱中国
/lab ising 2.269 240
/eng control bode 1 | 1 0.4 1
```

参数记法遵循常见 CLI 约定：

```text
<arg>       必填位置参数
[arg]       可选位置参数
{a|b}       必须从候选中选一个
[{a|b}]     可选的枚举项
[arg ...]   可重复的可选参数
```

图片、CIF/mCIF 等不是位置参数，会在 Help 中单独列为附加输入。

**自然语言 Agent**位于所有正式插件之上。它默认可以调用全部正式非 Legacy 能力；会根据问题组合多个工具结果、压缩冗余文本并只保留最有价值的证据。图片类插件结果先被捕获为临时媒体资产，只有 Agent 判断确实值得展示时才发送，而不是每调用一次插件就自动把所有图塞进回复。

如果用户需要工具的原始结果，Agent 可以在合适时给出对应完整命令，但不会机械地在每条回答后追加命令提示。

## Help 与模块开关

`/help` 默认生成本地 Typst 排版的 geek 风格图片卡片，也可以按群切换为纯文本：

```text
/help style image
/help style text
```

Help 内容由 live registry 生成，支持逐层导航，例如：

```text
/help math
/help math oeis
/help lang tangut
/help lab ising
```

正式模块默认全部开启。群主/群管理员可以使用 AstrBot 原生 session-level plugin 配置的 Doge 外壳，对**当前群**独立启停模块：

```text
/admin modules list
/admin modules off games
/admin modules on games
/admin modules reset
```

`core` 与 `admin` 是恢复入口，不能被群内关闭；Legacy 不在正式模块列表中。模块关闭同时影响直接命令和 Agent Tools。

## 仓库结构

```text
.
├── doge-v5/                 # 当前主线：AstrBot 插件化实现
│   ├── plugins/             # doge_* 正式插件 + doge_shared 共享层
│   ├── persona/             # 生产 persona 源文件
│   ├── tests/               # 回归、渲染、能力/历史覆盖测试
│   ├── tools/               # runtime materialize / install / docs generator
│   ├── plugin_manifest.json # 可部署插件真值表
│   ├── HELP.md              # registry 自动生成的正式帮助
│   └── LEGACY.md            # 历史能力索引
├── doge-v4/                 # 上一代 AstrBot 实现，保留用于回溯
├── doge-v3/                 # Mirai 时代历史源码
└── doge-v2/                 # CQP 时代可恢复的部分源码
```

v5 的内部结构、部署边界和开发规范见 [`doge-v5/README.md`](doge-v5/README.md)。

## 部署 v5

本仓库没有把所有目录直接复制进 AstrBot。应由 manifest 物化需要的 profile。

先检查：

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins \
  --profile default \
  --dry-run
```

确认后安装默认正式插件，并安装 Persona/运行时策略：

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins \
  --profile default \
  --mode symlink \
  --force

python3 doge-v5/tools/install_runtime_profile.py \
  --runtime /path/to/AstrBot
```

`default` 不包含 Legacy。`legacy` 是显式 opt-in；`planned`、`merged` 项不会被当成独立生产插件物化。

具体依赖、平台配置与第三方边界请继续阅读 v5 文档和各插件实现。不要把 API key、QQ 凭据或 provider token 写入仓库。

## 开发原则

欢迎 PR。v5 不是简单堆命令，新增功能至少应满足以下约束：

1. **Registry first**：公开功能进入 capability registry，并明确 canonical path、别名、必填/可选参数、附件输入和简要说明；
2. **单一事实源**：Help、统计、Agent 自我认知不分别手写另一套功能表；
3. **真实结果优先**：科研/检索/状态能力应返回真实数据或明确失败，不用 silent mock 冒充成功；
4. **异步与隔离**：避免阻塞 AstrBot 主事件循环，不把用户代码直接执行在 Doge 宿主机；
5. **图片可控**：图片输出必须有明确价值，Agent 场景下允许上层选择是否展示；
6. **历史可追溯**：不因重构随意删除有价值的旧能力；无法继续生产使用的功能进入 Legacy 并记录状态；
7. **测试与回滚**：修改 runtime 前先测试并保留可恢复备份。

更详细的架构说明见 [`doge-v5/PLUGIN_ARCHITECTURE.md`](doge-v5/PLUGIN_ARCHITECTURE.md)，事实性返回原则见 [`doge-v5/TRUTHFULNESS.md`](doge-v5/TRUTHFULNESS.md)，人格说明见 [`doge-v5/PERSONA.md`](doge-v5/PERSONA.md)。

## 历史

豆子始于 2019 年，并长期活跃于数学吧相关群聊。不同年代更换过 CQA、CQP、Mirai 与 AstrBot 等底层；旧版本目录的价值主要是历史回溯、功能考古和迁移参考，而不是推荐部署。

- `v2`：CQP 时代，仓库只保存了能恢复的部分源码；
- `v3`：Mirai 时代，历史实现相对完整；
- `v4`：第一代 AstrBot 主线；
- `v5`：当前主线，对 v2-v4 进行能力级重构并引入统一 registry、Agent 编排与 Legacy containment。

感谢历代贡献者、使用者以及曾对底层部署和机器人开发提供帮助的朋友。
