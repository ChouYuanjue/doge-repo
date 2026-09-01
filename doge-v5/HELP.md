# Doge v5 command guide

Doge 的功能按能力域组织。先用 /help <分类> 找方向，再用 /help <指令> 或 /help <指令> <子功能> 看具体用法。

## 开始 / 状态 (`start`)

认识当前实例、查看运行状态与使用统计。

### `/help`

分层帮助导航。

用法：

- `/help`
- `/help <分类>`
- `/help <指令>`
- `/help <指令> <子功能>`

例子：

- `/help research`
- `/help game`
- `/help game mine`
- `/help lang tangut`

### `/ver`

显示当前 Doge/AstrBot/Python/Git 的精确版本与运行能力规模。

用法：

- `/ver`

### `/status`

查看此刻服务器和 Doge 链路状态：负载、内存、磁盘、AstrBot RSS 与关键端口。

用法：

- `/status`

### `/statics`

查看累计使用统计与产品规模：消息、命令、平台、LLM token、插件、指令和 Agent Tool。

用法：

- `/statics`

## 检索 / 科研 (`research`)

论文、知识检索，以及生化环材、天文和临床数据。

### `/lookup`

有来源的通用知识/计算查询；优先可靠公开源，不把 LLM 猜测冒充检索结果。

用法：

- `/lookup wiki <主题>`
- `/lookup wd <实体>`
- `/lookup wa <问题>`

Wolfram 仅在配置可用时启用。

### `/paper`

论文发现、引用链、开放全文与引文查询。

用法：

- `/paper <子功能> ...`

例子：

- `/paper search retrieval augmented generation`

### `/bio`

蛋白、结构、序列、通路与靶点查询。

用法：

- `/bio <子功能> ...`

### `/chem`

化学结构、PubChem 与 ChEMBL。

用法：

- `/chem <子功能> ...`

### `/mat`

材料数据库、CIF 晶体结构与粉末衍射。

用法：

- `/mat <子功能> ...`

例子：

- `/mat crystal info <CIF>`
- `/mat crystal powder <CIF>`

### `/astro`

天体、系外行星和 ADS 文献。

用法：

- `/astro <子功能> ...`

### `/trial`

ClinicalTrials.gov 临床试验查询。

用法：

- `/trial <关键词或编号>`

## 计算机 / AI (`compute`)

数学、轻量 AI/CS 实验和远端代码执行。

### `/math`

数学计算、进制、π、OEIS 等轻量数学工具。

用法：

- `/math <子功能> ...`

### `/ai`

不下载大模型的 AI 内部机制实验室。

用法：

- `/ai grad <表达式> | x=...`
- `/ai bpe <merge数> <文本>`

例子：

- `/ai grad relu(x*y + x**2) | x=2 y=-1`
- `/ai bpe 24 tokenizer为什么会把中文拆开`

### `/cs`

计算机科学小实验：自动机与图算法。

用法：

- `/cs regex <Python-style regex>`
- `/cs pagerank <边列表>`

例子：

- `/cs regex (a|b)*abb`
- `/cs pagerank A>B,B>C,C>A,A>C`

### `/run`

在受限远端编译/运行后端执行小段代码，不在 Doge 宿主机直接跑用户代码。

用法：

- `/run <语言> <代码>`

有输入、输出和超时限制。

## 排版 / 图形 / 工程 (`create`)

把公式、Markdown、代码、图表和工程系统变成可分享的结果。

### `/md`

Markdown 出版：聊天卡片、A4 文档 PNG 或真正 PDF。

用法：

- `/md card <Markdown>`
- `/md doc <Markdown>`
- `/md pdf <Markdown>`

### `/snippet`

代码/diff/终端输出的专业排版卡片。

用法：

- `/snippet <语言> [--hl=行号] <代码>`

例子：

- `/snippet python --hl=2-4 def f(x): ...`

### `/tex`

TeX/LaTeX 公式与文档渲染。

用法：

- `/tex <TeX>`

### `/typst`

直接使用 Typst 排版。

用法：

- `/typst <Typst source>`

### `/diagram`

结构图与数据可视化：本地 Graphviz、Vega-Lite，及 Mermaid。

用法：

- `/diagram graphviz <DOT>`
- `/diagram mermaid <source>`
- `/diagram vegalite <JSON>`

### `/eng`

工程实验室：Schemdraw 电路与 python-control 经典控制系统。

用法：

- `/eng circuit <描述>`
- `/eng control bode|step|impulse|nyquist|root ...`

### `/lab`

数学、物理和复杂系统的直观科学实验。

用法：

- `/lab <实验> ...`

## 语言学 (`language`)

西夏文、汉字历史音系、RRPL 与构造语言。

### `/lang`

Language Lab：西夏文、汉字音系、RRPL 与 R'lyehian/Cthuvian。

用法：

- `/lang tangut ...`
- `/lang han ...`
- `/lang rrpl ...`
- `/lang cthuvian ...`

## 游戏 / 群聊实验 (`play`)

小游戏、解谜、概念炼金和荒诞竞技场。

### `/game`

群聊游戏与解谜统一入口。

用法：

- `/game 24 ...`
- `/game nc ...`
- `/game signal ...`
- `/game mine ...`
- `/game sudoku ...`
- `/game dice ...`

例子：

- `/game mine normal`
- `/game sudoku hard`
- `/game dice d20adv 察觉 15`

### `/fuse`

把两个概念炼成可持续复用的群聊物件。

用法：

- `/fuse <概念A> + <概念B>`

### `/arena`

荒诞能力卡与约束条件驱动的竞技场。

用法：

- `/arena <子功能> ...`

## 媒体 / 小工具 (`media`)

图片识别、幻影坦克和少量不值得单独成域的小工具。

### `/media`

视觉小实验：AnimeTrace 图片识别与本地幻影坦克。

用法：

- `/media trace anime|gal [图片]`
- `/media mirage gray|color [两张图片]`

### `/util`

有用但不值得单独成域的小工具：codec、天气、APOD、Bing 等。

用法：

- `/util <子功能> ...`

## 管理 (`admin`)

AstrBot 框架级会话与管理指令，统一收在 /admin 下。

### `/admin`

AstrBot 框架级指令命名空间；普通 Doge 功能不放这里。

用法：

- `/admin help`
- `/admin sid`
- `/admin reset|stop|new|stats`
- `/admin set|unset ...`
- `/admin name|provider|dashboard_update ...`

部分子命令仅管理员可用。

## 下钻帮助

### `/help game mine`

经典扫雷，首击安全；支持开格、标雷、周边清扫。

用法：

- `/game mine easy|normal|hard`
- `/game mine open A1 [B2 ...]`
- `/game mine mark A1`
- `/game mine sweep A1`
- `/game mine board|end`

### `/help game sudoku`

唯一解数独，3 次错误机会，本地渲染棋盘。

用法：

- `/game sudoku easy|normal|hard`
- `/game sudoku A1 5`
- `/game sudoku show|reveal|end`

### `/help game dice`

Roll20 风格骰池：优势/劣势、keep/drop、爆炸骰、FATE、重骰、成功计数和 DC。

用法：

- `/game dice d20`
- `/game dice 4d6kh3`
- `/game dice d6!`
- `/game dice 3d6>3`
- `/game dice d20adv 察觉 15`

### `/help game 24`

24 点；wild 模式额外允许位运算。

用法：

- `/game 24 new`
- `/game 24 wild`
- `/game 24 <表达式>`
- `/game 24 reveal`

### `/help game nc`

Nine Men's Morris / 九子棋。

用法：

- `/game nc start|join|board|end`
- `/game nc A1`
- `/game nc A1-A2`
- `/game nc x B4`

### `/help game signal`

多层编码解密接力。

用法：

- `/game signal new easy|normal|hard`
- `/game signal hint|show`
- `/game signal solve <完整答案>`

### `/help lang tangut`

西夏文字典、GX/GHC 拟音与字典 grounding 的双向翻译。

用法：

- `/lang tangut <子功能> ...`

### `/help lang han`

通过音典 Web 后端比较中古、上古、方言和域外汉字音。

用法：

- `/lang han <汉字>`
- `/lang han <汉字> @ <语言筛选>`
- `/lang han find <语言关键词>`

### `/help lang rrpl`

RRPL 结构描述递归展开并本地渲染。

用法：

- `/lang rrpl <RRPL/汉字引用表达式>`

### `/help lang cthuvian`

固定上游 R'lyehian/Cthuvian Translator 的正反向与高语体翻译。

用法：

- `/lang cthuvian to <文本>`
- `/lang cthuvian high <文本>`
- `/lang cthuvian from <文本>`

### `/help media trace`

AnimeTrace 动漫/Gal 图片识别。

用法：

- `/media trace anime [图片]`
- `/media trace gal [图片]`

### `/help media mirage`

本地 Pillow/NumPy 幻影坦克，不依赖付费 API。

用法：

- `/media mirage gray [两张图片]`
- `/media mirage color [两张图片]`
