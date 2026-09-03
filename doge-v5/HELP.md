# Doge v5 command guide

本文件由 `capability_registry.json` 自动生成；运行时 `/help`、功能统计、命令归一化和 Agent 能力认知使用同一份注册表。

```text
Doge CLI

USAGE
  /help <group>
  /help <command>
  /help <command> <subcommand>

GROUPS
  system       4  系统 / 状态
             认识当前实例、查看运行状态与使用统计。
  research    59  检索 / 科研
             论文、知识检索，以及生化环材、天文和临床数据。
  compute     25  数学 / 计算机 / AI
             精确与符号数学、形式化入口，以及轻量 AI/CS 和远端代码执行。
  create      77  排版 / 图形 / 工程
             排版、结构图、工程系统，以及以图像/动画展示机制的科学实验。
  language    14  语言学
             西夏文、汉字历史音系、RRPL 与构造语言。
  play        38  游戏 / 群聊实验
             小游戏、解谜、概念炼金、荒诞竞技场与可按群开启的社交增强。
  media        9  媒体 / 小工具
             图片识别、幻影坦克和少量不值得单独成域的小工具。
  admin       15  管理
             AstrBot 框架级会话与管理指令，统一收在 /admin 下。
  legacy      81  Legacy / 历史博物馆（默认不加载）
             v2-v4 旧入口、迁移状态与仍可追溯的历史子功能。

QUICK START
  /help research        论文与真实科研数据源
  /help compute         CS / AI / 数学 / 代码
  /help lang            Language Lab
  /help lang tangut     西夏文双向翻译、拟音、字典和渲染
  /help game            全部游戏
  /help lab             全部科学小实验
  /help legacy          历史功能状态

SCALE
  顶层指令       32
  正式叶子功能   242
  正式调用形式   514  （含 272 个兼容别名）
  Legacy 叶子    81

SYNTAX
  <arg> 必填    [arg] 可选    {a|b} 必选其一    [{a|b}] 可选其一
  [arg ...] 可重复    + <附件> 表示同一条消息附带的非文本输入
  帮助只推荐 canonical 写法；旧别名仍可调用，但统计会归一到同一个功能。
  `/` 同时是唤醒符；没有命中本表的 `/anything` 不会被算作指令。
```

## 系统 / 状态 (`system`)

认识当前实例、查看运行状态与使用统计。

### `/help`

```text
COMMAND  /help
分层帮助导航。

USAGE
  /help [topic]

PARAMETERS
  [topic]
    可选。分类、顶层指令或更深的子功能路径，例如 research、math oeis、lang tangut；省略时显示总览。

EXAMPLES
  /help
  /help math oeis
  /help lang tangut

ABOUT
  分层查看分类、指令和子功能帮助。

BACK
  /help
```

### `/ver`

```text
COMMAND  /ver
显示当前 Doge/AstrBot/Python/Git 的精确版本与运行能力规模。

USAGE
  /ver

ABOUT
  显示精确版本与产品规模。

BACK
  /help
```

### `/status`

```text
COMMAND  /status
查看此刻服务器和 Doge 链路状态：负载、内存、磁盘、AstrBot RSS 与关键端口。

USAGE
  /status

ABOUT
  查看服务器与本地链路实时状态。

BACK
  /help
```

### `/statics`

```text
COMMAND  /statics
查看累计使用统计与产品规模：消息、命令、平台、LLM token、插件、指令和 Agent Tool。

USAGE
  /statics

ABOUT
  查看真实使用统计、功能规模和 LLM 用量。

BACK
  /help
```

## 检索 / 科研 (`research`)

论文、知识检索，以及生化环材、天文和临床数据。

### `/lookup`

```text
COMMAND  /lookup
有来源的通用知识/计算查询；优先可靠公开源，不把 LLM 猜测冒充检索结果。

DIRECT
  /lookup <query>
    自动选择真实百科/Wikidata 来源。

SUBCOMMANDS
  wiki             百科查询。
    /lookup wiki <query>
  entity           Wikidata/QLever 结构化事实。
    /lookup entity <query>
  web              实时网页搜索：匿名 AnySearch，无需付费 API key；失败自动回退公开 Bing 搜索页。
    /lookup web <query>
  read             提取公开网页正文；拒绝本机、私网、链路本地和保留地址。
    /lookup read <url>
  wa               Wolfram|Alpha 查询（配置可用时）。
    /lookup wa <query>
  en               英文百科 + Wikidata 查询。
    /lookup en <query>

NEXT
  /help lookup wiki

BACK
  /help
```

### `/chaoli`

```text
COMMAND  /chaoli
超理论坛只读浏览：最新/分板主题、帖子与楼层上下文、用户公开活动、帖子引用链；首版不依赖站内搜索。

SUBCOMMANDS
  latest           查看超理最新主题流，可指定板块和数量。
    /chaoli latest [板块] [数量]
  channel          按数学、物理、化学、生物、技术、语言、社科、科幻、合集等板块浏览主题。
    /chaoli channel <板块> [数量]
  read             读取超理帖子；长楼保留首部与末部，避免一次刷屏。
    /chaoli read <帖子号|链接>
  floor            精确读取指定楼层。
    /chaoli floor <帖子号> <楼层>
  context          读取指定楼层及前后 1-3 层上下文。
    /chaoli context <帖子号> <楼层> [1-3]
  outline          长帖楼层提纲：列出楼层作者、时间和短摘要，便于再用 context 深读。
    /chaoli outline <帖子号|链接>
  user             按用户名、用户 ID 或用户链接定位超理用户，并查看公开主页与近期公开活动。
    /chaoli user <用户名|用户ID|链接>
  links            抽取帖子正文中引用的其他超理帖子，沿引用链继续阅读。
    /chaoli links <帖子号|链接>
  preview          一屏预览超理帖子；群聊中的纯 Chaoli 帖子链接也会自动轻量展开。
    /chaoli preview <帖子号|链接>
  status           检查 Chaoli 专用选择性代理与论坛首页是否可达。
    /chaoli status

NEXT
  /help chaoli latest

BACK
  /help
```

### `/paper`

```text
COMMAND  /paper
论文发现、引用链、开放全文与引文查询。

SUBCOMMANDS
  search           论文搜索
    /paper search <query>
  doi              精确 DOI/标识符书目查询
    /paper doi <query>
  cited            被引论文
    /paper cited <query>
  refs             参考文献
    /paper refs <query>
  related          相关论文
    /paper related <query>
  oa               开放获取定位
    /paper oa <query>
  bib              BibTeX/RIS 等引用格式
    /paper bib <query>
  check            撤稿/更正检查
    /paper check <query>
  dataset          关联数据集
    /paper dataset <query>
  pubmed           PubMed/PMC 查询
    /paper pubmed <query>
  arxiv            arXiv 查询
    /paper arxiv <query>
  author           作者查询
    /paper author <query>
  org              机构查询
    /paper org <query>
  affil            按 affiliation 查询机构
    /paper affil <query>

NEXT
  /help paper search

BACK
  /help
```

### `/bio`

```text
COMMAND  /bio
蛋白、结构、序列、通路与靶点查询。

SUBCOMMANDS
  protein          UniProt 蛋白
    /bio protein <query>
  domain           InterPro 结构域
    /bio domain <query>
  gene             Ensembl 基因
    /bio gene <query>
  pdb              PDB 结构
    /bio pdb <query>
  af               AlphaFold 结构
    /bio af <query>
  variant          变异查询
    /bio variant <query>
  blast            提交 BLAST
    /bio blast <query>
  blastget         获取 BLAST 结果
    /bio blastget <query>
  pathway          Reactome 通路
    /bio pathway <query>
  target           Open Targets 靶点
    /bio target <query>
  map              ID 映射
    /bio map <query>

NEXT
  /help bio protein

BACK
  /help
```

### `/chem`

```text
COMMAND  /chem
化学结构、PubChem 与 ChEMBL。

SUBCOMMANDS
  formula          分子式查询/转换
    /chem formula <query>
  smiles           SMILES 查询/转换
    /chem smiles <query>
  names            名称查询
    /chem names <query>
  inchikey         InChIKey 查询
    /chem inchikey <query>
  image            结构图
    /chem image <query>
  info             PubChem 详情
    /chem info <query>
  drug             ChEMBL 药物机制
    /chem drug <query>
  target           ChEMBL/Open Targets 靶点
    /chem target <query>

NEXT
  /help chem formula

BACK
  /help
```

### `/mat`

```text
COMMAND  /mat
材料数据库、CIF 晶体结构与粉末衍射。

SUBCOMMANDS
  find             OPTIMADE 跨数据库结构查询。
    /mat find <formula/filter>
  providers        OPTIMADE provider 列表。
    /mat providers
  crystal           2 功能  真实 CIF / XRD

NEXT
  /help mat find

BACK
  /help
```

#### `/help mat crystal`

```text
COMMAND  /mat crystal
真实 CIF / XRD

SUBCOMMANDS
  info             真实 CIF/mCIF 晶胞信息。
    /mat crystal info
  powder           真实 CIF/mCIF powder XRD。
    /mat crystal powder [energy_keV] [width]

NEXT
  /help mat crystal info

BACK
  /help mat
```

### `/astro`

```text
COMMAND  /astro
天体、系外行星和 ADS 文献。

SUBCOMMANDS
  object           SIMBAD 天体对象
    /astro object <query>
  exo              系外行星
    /astro exo <query>
  ads              ADS 文献
    /astro ads <query>

NEXT
  /help astro object

BACK
  /help
```

### `/trial`

```text
COMMAND  /trial
ClinicalTrials.gov 临床试验查询。

SUBCOMMANDS
  search           ClinicalTrials.gov 试验搜索。
    /trial search <query>
  get              ClinicalTrials.gov NCT 详情。
    /trial get <NCT ID>

NEXT
  /help trial search

BACK
  /help
```

## 数学 / 计算机 / AI (`compute`)

精确与符号数学、形式化入口，以及轻量 AI/CS 和远端代码执行。

### `/math`

```text
COMMAND  /math
精确/符号计算、代数与微积分、数论、统计、OEIS、WA 和形式化数学入口；结果以计算/文本为主。

SUBCOMMANDS
  calc             数学表达式计算。
    /math calc <表达式>
  base             进制转换。
    /math base <数> <原进制> <目标进制>
  pi               查询 π 指定位数片段。
    /math pi <起点> <位数>
  oeis             查询 OEIS 数列/关键词。
    /math oeis <数列或关键词>
  numeric          数学函数与高精度数值求值（SymPy）。
    /math numeric <表达式> [--digits <位数>]
  simplify         符号化简（SymPy）。
    /math simplify <表达式>
  expand           代数展开（SymPy）。
    /math expand <表达式>
  factor           符号因式分解（SymPy）。
    /math factor <表达式>
  solve            解方程或求表达式零点。
    /math solve <方程/表达式> [--var <变量>]
  diff             符号求导。
    /math diff <表达式> [--var <变量>] [--order <阶数>]
  integrate        不定积分或定积分。
    /math integrate <表达式> [--var <变量>] [--from <下限> --to <上限>]
  limit            符号极限。
    /math limit <表达式> --to <趋近点> [--var <变量>] [--dir {+|-|+-}]
  factorint        整数素因子分解。
    /math factorint <整数>
  prime            素性检查并给出相邻素数。
    /math prime <整数>
  stats            一维描述统计。
    /math stats <数> [数 ...]
  wa               Wolfram|Alpha LLM API 计算/知识查询。
    /math wa <query>
  formal            4 功能  Lean / Coq(Rocq) / Rzk 轻量形式化入口

NEXT
  /help math calc

BACK
  /help
```

#### `/help math formal`

```text
COMMAND  /math formal
Lean / Coq(Rocq) / Rzk 轻量形式化入口

DIRECT
  /math formal
    Lean / Coq(Rocq) / Rzk 轻量形式化入口概览。

SUBCOMMANDS
  lean             生成 Lean 4 / Mathlib starter，并把源码带入 Lean Web。
    /math formal lean [Lean code]
  coq              Coq/Rocq 的 jsCoq 浏览器入口与 starter。
    /math formal coq [Coq code]
  rzk              Rzk 单文件 playground 与 starter。
    /math formal rzk [Rzk code]

NEXT
  /help math formal lean

BACK
  /help math
```

### `/ai`

```text
COMMAND  /ai
不下载大模型的 AI 内部机制实验室。

SUBCOMMANDS
  grad             micrograd 自动微分计算图与反向梯度。
    /ai grad <expr> | x=...
  bpe              minBPE byte-level merge/token 可视化。
    /ai bpe [merges] <text>

NEXT
  /help ai grad

BACK
  /help
```

### `/cs`

```text
COMMAND  /cs
计算机科学小实验：自动机与图算法。

SUBCOMMANDS
  regex            Regex→ε-NFA→DFA→最小 DFA。
    /cs regex <python-style regex>
  pagerank         PageRank 图重要性计算与可视化。
    /cs pagerank <边列表>

NEXT
  /help cs regex

BACK
  /help
```

### `/run`

```text
COMMAND  /run
在受限远端编译/运行后端执行小段代码，不在 Doge 宿主机直接跑用户代码。

USAGE
  /run <语言> <代码>

ABOUT
  受限远端代码执行。

BACK
  /help
```

## 排版 / 图形 / 工程 (`create`)

排版、结构图、工程系统，以及以图像/动画展示机制的科学实验。

### `/md`

```text
COMMAND  /md
Markdown 出版：聊天卡片、A4 文档 PNG 或真正 PDF。

SUBCOMMANDS
  card             Markdown 自适应分享卡。
    /md card <Markdown>
  doc              Markdown A4 多页 PNG。
    /md doc <Markdown>
  pdf              Markdown 真 PDF。
    /md pdf <Markdown>

NEXT
  /help md card

BACK
  /help
```

### `/snippet`

```text
COMMAND  /snippet
代码/diff/终端输出的专业排版卡片。

USAGE
  /snippet <语言> [--title=...] [--hl=...] <代码>

ABOUT
  代码/diff/终端输出专业排版卡。

BACK
  /help
```

### `/tex`

```text
COMMAND  /tex
TeX/LaTeX 公式与文档渲染。

SUBCOMMANDS
  smart            TeX 智能渲染：完整文档自动 Tectonic，公式/片段轻量渲染。
    /tex smart <TeX公式、片段或完整文档>
  doc              完整 LaTeX 文档用本机 Tectonic 编译为 PDF。
    /tex doc <完整 LaTeX 文档>
  native           TeX 原生路径渲染。
    /tex native <TeX>
  local            TeX 本地路径渲染。
    /tex local <TeX>

NEXT
  /help tex smart

BACK
  /help
```

### `/typst`

```text
COMMAND  /typst
直接使用 Typst 排版。

SUBCOMMANDS
  card             Typst 分享卡。
    /typst card <Typst>
  math             Typst 数学模式。
    /typst math <Typst>
  doc              Typst 文档模式。
    /typst doc <Typst>
  chat             Typst 聊天版式。
    /typst chat <Typst>

NEXT
  /help typst card

BACK
  /help
```

### `/diagram`

```text
COMMAND  /diagram
结构图与数据可视化：本地 Graphviz、Vega-Lite，及 Mermaid。

SUBCOMMANDS
  graphviz         本地 Graphviz DOT
    /diagram graphviz <source>
  mermaid          Mermaid 图
    /diagram mermaid <source>
  vegalite         本地 Vega-Lite 数据可视化
    /diagram vegalite <source>
  formats          查看稳定图形后端。
    /diagram formats

NEXT
  /help diagram graphviz

BACK
  /help
```

### `/eng`

```text
COMMAND  /eng
工程实验室：Schemdraw 电路与 python-control 经典控制系统。

SUBCOMMANDS
  circuit           4 功能  电路
  control           5 功能  经典控制

NEXT
  /help eng circuit

BACK
  /help
```

#### `/help eng circuit`

```text
COMMAND  /eng circuit
电路

SUBCOMMANDS
  rc               RC 电路图
    /eng circuit rc [R] [C]
  rlc              RLC 电路图
    /eng circuit rlc [R] [L] [C]
  divider          分压器电路图
    /eng circuit divider [R1] [R2]
  series           自由串联元件电路图
    /eng circuit series <component> [component ...]

NEXT
  /help eng circuit rc

BACK
  /help eng
```

#### `/help eng control`

```text
COMMAND  /eng control
经典控制

SUBCOMMANDS
  bode             bode 控制系统响应。
    /eng control bode <num> | <den>
  step             step 控制系统响应。
    /eng control step <num> | <den>
  impulse          impulse 控制系统响应。
    /eng control impulse <num> | <den>
  nyquist          nyquist 控制系统响应。
    /eng control nyquist <num> | <den>
  root             root 控制系统响应。
    /eng control root <num> | <den>

NEXT
  /help eng control bode

BACK
  /help eng
```

### `/lab`

```text
COMMAND  /lab
可视化、模拟和直觉实验：用图像/动画观察数学、物理与复杂系统；不作为通用求解器。

SUBCOMMANDS
  fractal           2 功能  分形
  chaos            Logistic map 分岔图。
    /lab chaos bifurcation [rmin] [rmax]
  attractor        Lorenz/Rössler/Clifford 吸引子。
    /lab attractor [{lorenz|rossler|clifford}]
  ca               Wolfram 一维元胞自动机。
    /lab ca [rule] [steps]
  number            2 功能  数论图形
  lsys             L-system 分形。
    /lab lsys [{dragon|hilbert|koch|plant}] [iterations]
  tiling           Penrose 铺砌。
    /lab tiling penrose [depth]
  wave             双源波干涉
    /lab wave [separation] [wavelength]
  field            电场线
    /lab field [{dipole|quadrupole|triple}]
  pendulum         双摆
    /lab pendulum [initial_angle_deg]
  orbit            三体 figure-eight 轨道
    /lab orbit [figure8]
  reaction         Gray-Scott 反应扩散
    /lab reaction [{spots|worms|mitosis|coral}]
  linear           二维线性映射
    /lab linear <a> <b> <c> <d>
  complex          复函数域着色
    /lab complex [{z|z2+1|z3-1|1/z|sin|exp}] [zoom]
  newton           Newton 分形
    /lab newton [degree] [zoom]
  ising            二维 Ising 模型
    /lab ising [T] [sweeps]
  percolation      渗流模型
    /lab percolation [p] [size]
  randommatrix     随机矩阵谱
    /lab randommatrix [{ginibre|goe}] [N]
  voronoi          Voronoi 几何
    /lab voronoi [points]
  bloch            Bloch 球
    /lab bloch [theta_deg] [phi_deg]
  relativity       Minkowski/狭义相对论图
    /lab relativity [beta]
  spectrum         FFT 频谱
    /lab spectrum [{sine|square|saw|chirp}] [frequency]
  sandpile         Abelian sandpile
    /lab sandpile [grains]
  ant              Langton 蚂蚁
    /lab ant [steps]
  moire            莫尔纹
    /lab moire [angle_deg] [spacing_px]
  orbital          氢样原子轨道切片
    /lab orbital [{1s|2px|2py|3dxy|3dz2}]
  lattice          晶格实空间投影
    /lab lattice [{sc|bcc|fcc|diamond}] [cells]
  xrd              理想晶格 XRD 教学模型
    /lab xrd [{sc|bcc|fcc|diamond}] [a] [wavelength]
  knot             数学结可视化
    /lab knot [{trefoil|figure8|torus}] [p] [q]
  brownian         布朗运动
    /lab brownian [walkers] [steps]
  sir              SIR 传染病模型
    /lab sir [R0] [infectious_days]
  predator         Lotka–Volterra 捕食者模型
    /lab predator [alpha] [beta] [delta] [gamma]
  lens             薄透镜成像
    /lab lens [focal] [object_distance]
  well             量子无限深势阱
    /lab well [n]
  diffraction      双缝/单缝衍射
    /lab diffraction [slit_sep] [slit_width] [wavelength]
  replicator       复制子动力学/RPS
    /lab replicator [bias]
  life              4 功能  可配置且可接续的 Life-like cellular automaton 动态 GIF：自定义初态、任意合法 B/S 规则、dead/wrap 边界与 per-group/session 最终棋盘状态。
  dla              Diffusion-limited aggregation
    /lab dla [particles]
  beats            拍频
    /lab beats [f1] [f2] [seconds]
  chladni          Chladni 板振型
    /lab chladni [m] [n]
  phyllotaxis      叶序/黄金角
    /lab phyllotaxis [angle_deg] [points]
  galton           Galton 板
    /lab galton [rows] [balls]
  lissajous        Lissajous 曲线
    /lab lissajous [fx] [fy] [phase_deg]

NEXT
  /help lab fractal

BACK
  /help
```

#### `/help lab fractal`

```text
COMMAND  /lab fractal
分形

SUBCOMMANDS
  mandelbrot       Mandelbrot 分形。
    /lab fractal mandelbrot [cx] [cy] [zoom]
  julia            Julia 分形。
    /lab fractal julia [c_re] [c_im] [zoom]

NEXT
  /help lab fractal mandelbrot

BACK
  /help lab
```

#### `/help lab number`

```text
COMMAND  /lab number
数论图形

SUBCOMMANDS
  ulam             Ulam 素数螺旋。
    /lab number ulam [size]
  mod              模乘圆。
    /lab number mod [multiplier] [points]

NEXT
  /help lab number ulam

BACK
  /help lab
```

#### `/help lab life`

```text
COMMAND  /lab life

DIRECT
  /lab life [seed] [steps] [rule] [dead|wrap] [size]
    可配置且可接续的 Life-like cellular automaton 动态 GIF：自定义初态、任意合法 B/S 规则、dead/wrap 边界与 per-group/session 最终棋盘状态。

SUBCOMMANDS
  continue         从当前群/会话最近一次 Life 最终棋盘继续真实演化；默认继承规则与边界，也可本次覆盖。
    /lab life continue [steps] [rule] [dead|wrap]
  status           查看当前群/会话保存的 Life generation、活细胞数、棋盘尺寸、规则与边界。
    /lab life status
  clear            清除当前群/会话保存的 Life 接续状态。
    /lab life clear

NEXT
  /help lab life continue

BACK
  /help lab
```

### `/fourier`

```text
COMMAND  /fourier
图片/SVG/文本轮廓的傅里叶旋转向量动画；延续 v4 Fourier，不是普通 FFT 频谱图。

SUBCOMMANDS
  mode             查看或设置每用户 merge/separate 轮廓处理模式。
    /fourier mode [{merge|separate}]
  svg              将 SVG 栅格化、提取轮廓并生成 DFT 旋转向量 GIF。
    /fourier svg <SVG源码>
  text             将文本字形提取为轮廓并生成 DFT 旋转向量 GIF。
    /fourier text <文本>
  image            从真实图片像素提取轮廓并用傅里叶旋转圆/向量逐帧描出 GIF。
    /fourier image [vectors] [frames]

NEXT
  /help fourier mode

BACK
  /help
```

## 语言学 (`language`)

西夏文、汉字历史音系、RRPL 与构造语言。

### `/lang`

```text
COMMAND  /lang
Language Lab：西夏文、汉字音系、RRPL 与 R'lyehian/Cthuvian。

SUBCOMMANDS
  tangut            6 功能  西夏文双向翻译 / 字典 / 拟音 / 渲染
  cthuvian          3 功能  R'lyehian / Cthuvian
  han               2 功能  汉字历史音系 / 方言
  rrpl              3 功能  RRPL · 递归部件语法 / 解释 / 渲染

NEXT
  /help lang tangut

BACK
  /help
```

#### `/help lang tangut`

```text
COMMAND  /lang tangut
西夏文双向翻译 / 字典 / 拟音 / 渲染

SUBCOMMANDS
  lookup           西夏文↔中文/英文词典查询。
    /lang tangut lookup <西夏文/中文/英文>
  gx               GX 拟音
    /lang tangut gx <西夏文>
  ghc              GHC 拟音
    /lang tangut ghc <西夏文>
  t2zh             西夏文→中文：词典 grounding 后保守整理。
    /lang tangut t2zh <西夏文>
  zh2t             中文→西夏文：exact-gloss grounding，未知项不乱译。
    /lang tangut zh2t <中文>
  render           西夏文 Noto Serif Tangut 渲染。
    /lang tangut render <西夏文>

NEXT
  /help lang tangut lookup

BACK
  /help lang
```

#### `/help lang cthuvian`

```text
COMMAND  /lang cthuvian
R'lyehian / Cthuvian

SUBCOMMANDS
  to               English→R’lyehian/Cthuvian 低语体翻译。
    /lang cthuvian to <English>
  high             English→Cthuvian 高语体：已有词走确定性 RC-1；新词由专用 DeepSeek 提案，经规则校验后永久双向入词典，高语体禁止 fallback。
    /lang cthuvian high <English>
  from             R’lyehian/Cthuvian→English gloss。
    /lang cthuvian from <RC-1>

NEXT
  /help lang cthuvian to

BACK
  /help lang
```

#### `/help lang han`

```text
COMMAND  /lang han
汉字历史音系 / 方言

DIRECT
  /lang han <汉字> [@ 语言筛选]
    MCPDict/Yindian 汉字跨时代/方言读音比较。

SUBCOMMANDS
  find             搜索音典语言变体。
    /lang han find <关键词>

NEXT
  /help lang han find

BACK
  /help lang
```

#### `/help lang rrpl`

```text
COMMAND  /lang rrpl
RRPL · 递归部件语法 / 解释 / 渲染

DIRECT
  /lang rrpl <RRPL/汉字引用表达式>
    RRPL 递归部件语言渲染；支持 0–8 米格笔画、横/竖 packing、括号分组与汉字部件引用。

SUBCOMMANDS
  syntax           查看 RRPL 完整核心语法与例子。
    /lang rrpl syntax
  explain          展开汉字引用并检查 RRPL packing/笔画结构。
    /lang rrpl explain <RRPL/汉字引用表达式>

NEXT
  /help lang rrpl syntax

BACK
  /help lang
```

## 游戏 / 群聊实验 (`play`)

小游戏、解谜、概念炼金、荒诞竞技场与可按群开启的社交增强。

### `/game`

```text
COMMAND  /game
群聊游戏与解谜统一入口。

SUBCOMMANDS
  dice             桌面骰池
    /game dice <expr>
  mine              6 功能  扫雷
  sudoku            5 功能  数独
  24                4 功能  24 点
  nc                5 功能  九子棋
  signal            4 功能  Signal 解密

NEXT
  /help game dice

BACK
  /help
```

#### `/help game mine`

```text
COMMAND  /game mine
扫雷

SUBCOMMANDS
  new              开始扫雷；首次开格保证安全。
    /game mine [{easy|normal|hard}]
  open             扫雷开格。
    /game mine open <cell> [cell ...]
  mark             扫雷：标雷
    /game mine mark <cell> [cell ...]
  sweep            扫雷：周边清扫
    /game mine sweep <cell> [cell ...]
  board            扫雷：查看棋盘
    /game mine board
  end              扫雷：结束扫雷
    /game mine end

NEXT
  /help game mine new

BACK
  /help game
```

#### `/help game sudoku`

```text
COMMAND  /game sudoku
数独

SUBCOMMANDS
  new              开始唯一解数独。
    /game sudoku [{easy|normal|hard}]
  set              填写数独格子。
    /game sudoku set <cell> <digit>
  show             查看数独棋盘
    /game sudoku show
  reveal           显示答案并结束
    /game sudoku reveal
  end              结束数独
    /game sudoku end

NEXT
  /help game sudoku new

BACK
  /help game
```

#### `/help game 24`

```text
COMMAND  /game 24
24 点

SUBCOMMANDS
  new              开始普通 24 点。
    /game 24 new
  wild             开始允许位运算的 24 点。
    /game 24 wild
  solve            提交 24 点表达式。
    /game 24 <表达式>
  reveal           显示 24 点答案。
    /game 24 reveal

NEXT
  /help game 24 new

BACK
  /help game
```

#### `/help game nc`

```text
COMMAND  /game nc
九子棋

DIRECT
  /game nc <action>
    九子棋放置、移动或吃子动作。

SUBCOMMANDS
  start            创建九子棋。
    /game nc start
  join             加入九子棋。
    /game nc join
  board            查看九子棋棋盘。
    /game nc board
  end              结束九子棋。
    /game nc end

NEXT
  /help game nc start

BACK
  /help game
```

#### `/help game signal`

```text
COMMAND  /game signal
Signal 解密

SUBCOMMANDS
  new              创建多层编码信号
    /game signal new [{easy|normal|hard}]
  hint             获取下一层提示
    /game signal hint
  show             查看当前信号
    /game signal show
  solve            提交完整解码答案
    /game signal solve <完整答案>

NEXT
  /help game signal new

BACK
  /help game
```

### `/fuse`

```text
COMMAND  /fuse
把两个概念炼成可持续复用的群聊物件。

DIRECT
  /fuse <素材A> + <素材B>
    生成/重现群聊概念炼金设定。

SUBCOMMANDS
  book             查看炼金图鉴。
    /fuse book [count]

NEXT
  /help fuse book

BACK
  /help
```

### `/arena`

```text
COMMAND  /arena
完整保留原 /wp 238 条手写弱能力；支持原味直接对决与高组合竞技场。

SUBCOMMANDS
  draw             从原 /wp 238 条弱能力中抽卡。
    /arena draw
  show             查看当前能力
    /arena show
  fight            原味弱能力直接对决
    /arena fight <@对手或QQ号>
  duel             带战场目标的竞技场对决：Dedicated DeepSeek 两阶段推演荒诞规则连锁。
    /arena duel <@对手或QQ号>
  chaos            原 /wp 多能力组合
    /arena chaos [{2|3}]
  deck             查看卡池/组合空间
    /arena deck

NEXT
  /help arena draw

BACK
  /help
```

### `/social`

```text
COMMAND  /social
群聊社交增强：读空气主动发言、语义大表情和模板 meme；自动能力默认按群关闭。

SUBCOMMANDS
  air              按群控制 AI 读空气回复与合适时机主动发言。
    /social air [{on|off|status}]
  emoji            按群控制自动收集、标签检索并发送大表情包。
    /social emoji [{on|off|status}]
  meme              3 功能  列出 v4 同路线 meme-generator 模板关键词。

NEXT
  /help social air

BACK
  /help
```

#### `/help social meme`

```text
COMMAND  /social meme

SUBCOMMANDS
  list             列出 v4 同路线 meme-generator 模板关键词。
    /social meme list [过滤词]
  info             查看 meme 模板所需图片、文字与标签。
    /social meme info <模板关键词>
  make             用成熟 meme-generator 引擎生成模板图；支持当前/引用图片、@用户与头像参数。
    /social meme make <模板关键词> [文字参数]

NEXT
  /help social meme list

BACK
  /help social
```

## 媒体 / 小工具 (`media`)

图片识别、幻影坦克和少量不值得单独成域的小工具。

### `/media`

```text
GROUP  media
媒体 / 小工具
图片识别、幻影坦克和少量不值得单独成域的小工具。

COMMANDS
  /media         4  视觉小实验：AnimeTrace 图片识别与本地幻影坦克。
  /util          5  有用但不值得单独成域的小工具：codec、天气、APOD、Bing 等。

NEXT
  /help media
  /help
```

#### `/help media trace`

```text
COMMAND  /media trace
动漫 / Gal 识图

SUBCOMMANDS
  anime            AnimeTrace 动漫识别。
    /media trace anime
  gal              AnimeTrace Galgame 识别。
    /media trace gal

NEXT
  /help media trace anime

BACK
  /help media
```

#### `/help media mirage`

```text
COMMAND  /media mirage
幻影坦克

SUBCOMMANDS
  gray             灰度幻影坦克。
    /media mirage gray
  color            彩色幻影坦克。
    /media mirage color

NEXT
  /help media mirage gray

BACK
  /help media
```

### `/util`

```text
COMMAND  /util
有用但不值得单独成域的小工具：codec、天气、APOD、Bing 等。

SUBCOMMANDS
  encode           URL/Unicode/Hex/Base64 编码。
    /util encode {url|unicode|hex|base64} <文本>
  decode           URL/Unicode/Hex/Base64 解码。
    /util decode {url|unicode|hex|base64} <文本>
  weather          Open-Meteo 天气查询。
    /util weather <place> [days]
  apod             NASA Astronomy Picture of the Day。
    /util apod [date]
  bing             Bing 当日壁纸。
    /util bing

NEXT
  /help util encode

BACK
  /help
```

## 管理 (`admin`)

AstrBot 框架级会话与管理指令，统一收在 /admin 下。

### `/admin`

```text
GROUP  admin
管理
AstrBot 框架级会话与管理指令，统一收在 /admin 下。

COMMANDS
  /admin        15  AstrBot 框架级指令命名空间；普通 Doge 功能不放这里。

NEXT
  /help admin
  /help
```

#### `/help admin modules`

```text
COMMAND  /admin modules

SUBCOMMANDS
  list             查看当前群正式 Doge 模块的启停状态。
    /admin modules list
  on               由群主/群管理员为当前群启用一个正式 Doge 模块。
    /admin modules on <module>
  off              由群主/群管理员为当前群关闭一个正式 Doge 模块；对应指令与 Agent Tool 同时停用。
    /admin modules off <module>
  reset            恢复当前群默认模块状态：全部正式非 Legacy 模块开启。
    /admin modules reset

NEXT
  /help admin modules list

BACK
  /help admin
```

## Legacy

Legacy 默认不加载。完整历史入口、状态和子功能见 [`LEGACY.md`](LEGACY.md)。
