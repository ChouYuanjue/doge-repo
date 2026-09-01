# Doge v5 Academic Spine

学术能力是 Doge v5 的一级产品面，不是“装一个 arXiv 插件”。它现在分成两条平行主干：本文件记录真实科研检索/数据库工作流；`PLAYGROUND.md` 则记录数学、物理、化学、工程中原本要开 Jupyter、Mathematica 或专用软件才能玩的可视化和模拟。两条线都要求把复杂操作压缩成群聊可直接使用的短命令。

## 设计原则

1. **工作流优先于数据库名**：用户问“这篇论文谁在引用、有没有开放全文、有没有撤稿记录”，不应被迫分别理解 Crossref/OpenAlex/Unpaywall。
2. **官方 API 优先**：REST/TAP/GraphQL/E-utilities > 官方 SDK > 网页抓取。避免为每个数据库安装一套 Python SDK。
3. **只读默认**：学术工具默认不写外部系统、不提交实验任务。唯一例外是 NCBI BLAST 这种官方计算任务，提交后只返回 RID。
4. **群聊输出要短**：默认 3–5 条结果和关键字段；复杂结果以后支持文件/图表输出，而不是刷屏。
5. **Agent 与命令共用 service**：命令层负责参数与展示，Agent Tool 调同一实现。
6. **密钥是增强项**：能匿名调用的服务默认可用；OpenAlex/ADS/Unpaywall 等密钥或邮箱只从环境变量读取。

## 已实现

### `/paper` — 文献基础设施

数据源：Crossref、OpenAlex、Unpaywall（配置 `UNPAYWALL_EMAIL` 后优先）、DataCite、Europe PMC、arXiv、ROR。

- `/paper search <query>` — OpenAlex 跨学科检索
- `/paper doi <DOI/标题>` — Crossref 规范元数据
- `/paper cited <DOI>` — 谁引用了它
- `/paper refs <DOI>` — 它引用了谁
- `/paper related <DOI>` — OpenAlex related works
- `/paper oa <DOI>` — 合法开放全文定位
- `/paper bib <DOI> [bibtex|ris|apa|gbt]` — DOI content negotiation，直接生成引用格式
- `/paper check <DOI>` — Crossref 更新/更正记录 + OpenAlex retraction flag
- `/paper dataset <query>` — DataCite 数据集/软件/研究输出
- `/paper pubmed <query>` — Europe PMC / PubMed 入口
- `/paper arxiv <query>` — arXiv Atom API；不要求用户安装 arxiv Python SDK
- `/paper author <name>` — OpenAlex 作者、引用、h-index、ORCID、机构
- `/paper org <name>` — ROR 机构检索
- `/paper affil <raw affiliation>` — 把论文中混乱的 affiliation 字符串自动匹配成 ROR ID

后续优先：Semantic Scholar recommendation/citation intent、OpenCitations、ORCID public record、引用网络 Mermaid、OA PDF 摘要/方法比较、Crossref Retraction Watch 更完整呈现。

### `/bio` — 生物信息统一入口

数据源：UniProt、InterPro、Ensembl、RCSB PDB、AlphaFold DB、Reactome、Open Targets、NCBI BLAST。

- `/bio protein <accession/gene>` — UniProt 蛋白摘要
- `/bio domain <UniProt>` — InterPro 家族/结构域
- `/bio gene <symbol/Ensembl>` — Ensembl 基因位置与注释
- `/bio variant <rsID>` — Ensembl variant、后果、映射、phenotype
- `/bio pdb <PDB ID>` — RCSB PDB 实验结构元数据
- `/bio af <UniProt>` — AlphaFold DB 预测、mean pLDDT、PDB/CIF/PAE
- `/bio pathway <query>` — Reactome pathway
- `/bio target <gene>` — Open Targets target 搜索 + tractability
- `/bio map <from> <to> <IDs>` — UniProt 官方异步 ID mapping；可直接 UniProt→PDB/Ensembl/GeneID/ChEMBL 等
- `/bio blast <sequence>` — 自动判断核酸/蛋白，提交 NCBI BLAST，返回 RID
- `/bio blastget <RID>` — 稍后获取 BLAST 结果；不让一次群聊请求长时间阻塞

后续优先：QuickGO、NCBI E-utilities 的 Gene/Nucleotide/Protein、RCSB sequence/structure similarity、AlphaMissense、Reactome enrichment、批量 ID mapping 文件输出。

### `/chem` — 化学与药物发现

原有 NCI Cactus 快速结构转换保留，同时加入 PubChem 和 ChEMBL：

- `/chem formula|smiles|names|inchikey|image <query>` — Cactus 快速转换
- `/chem info <query>` — PubChem CID、分子式、分子量、SMILES、InChIKey
- `/chem drug <query>` — ChEMBL molecule + drug mechanism
- `/chem target <query>` — ChEMBL target search

后续优先：PubChem 2D similarity/substructure、ChEMBL activity/assay/IC50/Kd、drug indication/warning、UniChem ID bridge、ChEMBL Beaker 标准化和结构描述符。

### `/mat` — 材料科学

使用 OPTIMADE 标准 API，而不是绑定 Materials Project SDK。

- `/mat find SiO2` — 从化学式抽取元素并构造标准 OPTIMADE filter
- `/mat find filter:<OPTIMADE filter>` — 专业用户直接使用完整过滤语法
- `/mat providers` — 官方 registry 中的 AFLOW、COD、Materials Cloud、MP、NOMAD、OQMD、JARVIS 等 provider

首个默认结构后端为 Materials Cloud MC3D PBE；后续将做 provider discovery + fan-out，在同一命令里跨多个 OPTIMADE 数据库聚合、去重和比较结构。

### `/astro` — 天文数据

- `/astro object <identifier>` — SIMBAD TAP/ADQL，不抓网页
- `/astro exo <planet/host>` — NASA Exoplanet Archive TAP
- `/astro ads <query>` — NASA ADS（配置 `NASA_ADS_TOKEN` 后启用）

后续优先：VizieR TAP、Gaia Archive TAP、NASA ADS metrics/export、坐标 cone search、星表 cross-match。

### `/trial` — 临床研究

- `/trial search <query>` — ClinicalTrials.gov v2
- `/trial get <NCT ID>` — 状态、phase、条件、入组、时间、sponsor、摘要

后续优先：按 condition/intervention/sponsor/location/status 形成自然的字段过滤；和 `/bio target`、`/chem drug` 串成“靶点→药物→临床试验”工作流。

## Agent Tools

当前学术工具不复制实现，而是直接暴露 service：

- `doge_paper`
- `doge_bio`
- `doge_chem`（已扩展）
- `doge_materials`
- `doge_astro`
- `doge_trials`

Agent 因此可以把多个工具串起来，例如：

- DOI → Crossref 元数据 → OpenAlex 引用链 → OA 地址 → retraction check
- TP53 → UniProt → InterPro → PDB/AlphaFold → Reactome → Open Targets
- imatinib → PubChem → ChEMBL → 靶点 → ClinicalTrials.gov
- Si/O → OPTIMADE 结构 → 后续本地结构分析

## 值得继续封装但不急于堆进核心的工具

- 数学：zbMATH Open、Mathlib/Lean proof check（建议隔离 runtime）、更完整符号计算
- 物理：INSPIRE HEP、PDG machine-readable API、HEPData
- 天文：VizieR、Gaia、NASA ADS metrics/export
- 地学：USGS/IRIS、PANGAEA、EarthChem
- 生医：QuickGO、ClinVar/NCBI Variation、Open Targets Genetics、GWAS Catalog
- 化学：UniChem、ChEBI、ChEMBL Beaker、PubChem structure similarity
- 通用数据：Zenodo/DataCite、Figshare API、Dryad、OSF
- PDF/论文理解：GROBID/Docling 作为可选本地 sidecar；不要把重量级文档解析硬塞进 core plugin

这些能力优先按“统一科研问题”编排，而不是继续增加 `/crossref`、`/uniprot`、`/pdb` 这种数据库品牌级顶层命令。
