# 豆子 Doge 仓库说明
![GitHub repo size](https://img.shields.io/github/repo-size/ChouYuanjue/doge-repo)
![GitHub last commit](https://img.shields.io/github/last-commit/ChouYuanjue/doge-repo)
![GitHub stars](https://img.shields.io/github/stars/ChouYuanjue/doge-repo)
![Line of Codes](https://img.shields.io/badge/code%20lines-38940-brightgreen)
> QQ 机器人「豆子 Doge」源码仓库导读与上手指南

本文件旨在帮助你**大致了解豆子**、**快速读懂仓库结构**、**了解各版本差异**、并**尽可能成功部署机器人**

---

**对此项目有疑问？**

可以直接在wiki提问！[DeepWiki](https://deepwiki.com/ChouYuanjue/doge-repo)

## 0. 简介

豆子 Doge 诞生于 2019 年，到如今历经四个版本。

`v1`活跃时间为 2019 年，采用 CQA 。仅有关键词回复和图灵api聊天两个功能，完全基于酷Q自带面板进行配置，不存在源码一说。

`v2`活跃时间为 2020 年，采用 CQP 。仓库中文件与`v2`实际功能不完全对应，只包含可以找到的少部分源文件。

- `v2`文档可参见: [v2_docs.pdf](doge-v2/v2_docs.pdf) （**注意**：此文档为早期版本，基本不包含此仓库中源文件所涉及的功能）

`v3`活跃时间为 2022 年，采用 Mirai。仓库基本实现全收录.

- `v3`文档可参见：[v3_docs.md](doge-v3/v3_docs.md) 或者 [豆子 Doge 说明文档](https://docs-doge.netlify.app)

`v4`为现行版本，采用 AstrBot。仓库实时更新。

- `v4`文档可参见：[v4_docs.md](doge-v4/v4_docs.md)，已整合入bot的知识库，可直接向bot提问来咨询详情

四个版本的豆子始终活跃于数学吧官群，在此对数吧群的各位表示感谢。豆子诞生的契机是认识了丽琪，复刻丽琪的功能也一度成为开发豆子的动力和目标。在开发过程中，丽琪的作者多次进行了倾力指导。没有丽琪，也就不会有如今的豆子。感谢伟大的丽琪之父fyr。特别鸣谢sym学长，在服务器方面不遗余力地进行了大量指导，让豆子得以成功摆脱本地部署的种种不便。

欢迎各位参与豆子的开发工作！



## 1. 我应该从哪个版本开始？

* **v4（doge-v4）— 当前版本**：基于 **AstrBot** 框架（Python）。如果你是首次部署或想获得最新功能，请从 v4 开始。
* **v3（doge-v3）— 旧版本**：基于 **Mirai** 框架（JVM）。仅用于回溯或研究旧实现，不建议部署。此版本分为四个子模块，其中主体为`mirai-native`和`mirai-jvm`。
* **v2（doge-v2）— 历史版本**：基于 **CQP** 的早期实现，生态已停运；如需复刻，通常需用 **go-cqhttp** / **mirai-native** / **MiraiCQ** 等替代底层。不建议部署。



## 2. 功能块/指令概览

```
.
├── doge-v2/
├── doge-v3/
│   ├── lua-mirai/
│   │   ├── jeffjoke
│   │   └── qs
│   ├── mirai-api-http/
│   │   └── chatlearning
│   ├── mirai-jvm/
│   │   ├── chat
│   │   ├── genshin
│   │   ├── mirage
│   │   ├── nasa
│   │   ├── nc
│   │   ├── netool
│   │   ├── px
│   │   ├── wa
│   │   └── yan
│   └── mirai-native/
│       └── epk/
│           ├── amuse
│           ├── anime
│           ├── ask
│           ├── bing
│           ├── chem
│           ├── chart
│           ├── cotool
│           ├── docs
│           ├── dream
│           ├── echo
│           ├── frun
│           ├── fru
│           ├── gan
│           ├── game
│           ├── gen
│           ├── gpt
│           ├── insult
│           ├── jianh
│           ├── law
│           ├── math
│           ├── meme
│           ├── phil
│           ├── pic-url
│           ├── poem
│           ├── repo
│           ├── run
│           ├── se
│           ├── siku
│           ├── style
│           ├── test
│           ├── tex
│           ├── toonify
│           ├── url-pic
│           ├── ver
│           └── yg
└── doge-v4/
    ├── apis
    ├── complex
    ├── cube
    ├── doubao
    ├── emojimix
    ├── fourier
    ├── genshin
    ├── gol
    ├── gomoku
    ├── honkai
    ├── latex
    ├── liblibapi
    ├── lyrics
    ├── mc
    ├── meme
    ├── mermaid
    ├── mirage
    ├── music
    ├── pack
    ├── pjsk
    ├── pokemon
    ├── poker
    ├── rrpl
    ├── run
    ├── soup
    ├── st
    ├── tangut
    ├── trace
    ├── typst
    ├── utex
    ├── vv
    ├── wa
    ├── wordle
    ├── wiki
    └── wp

```



## 3. 快速上手（v4 / AstrBot）

### 3.1 先决条件

* **Python**：建议 3.10+
* **平台**：QQ / QQ 频道 （仅在 aiocqhttp 端进行过部署，其他平台不保证成功）
* **依赖与配置**：运行`pip install -r requirements.txt`安装依赖的库(可能有冗余)。为了bot的流畅运行，建议预留1G左右内存。
* **协议端**：建议安装 NapCat 并进行登录，配置反向 Websocket 待用。其余实现请自行参考有关文档。

### 3.2 部署路径

本项目未在AstrBot进行发布，请手动部署。以下全部为linux端部署教程。

**方式 A：Docker（推荐）**

1. 安装 Docker / Docker Compose。
2. 使用以下指令直接部署：
```
sudo docker run -itd -p 6180-6200:6180-6200 -p 11451:11451 -v $PWD/data:/AstrBot/data -v /etc/localtime:/etc/localtime:ro -v /etc/timezone:/etc/timezone:ro --name astrbot m.daocloud.io/docker.io/soulter/astrbot:latest
```
该操作会将容器中的`/AstrBot/data`目录映射到`~/astrbot/data`。如需映射其他目录请自行修改以上指令。

3. 将`doge-v4/`下的文件复制到`~/astrbot/data/plugins/`。

4. 通过面板重启bot以加载插件。

（如果不会使用docker不建议使用此方案部署，容易滋生问题。）

**方式 B：本地运行**

1. 克隆AstrBot仓库，切换路径至仓库目录。

2. 运行以下指令：
```
uv sync
uv run main.py
```

3. 将 `doge-v4/` 下文件复制到`/AstrBot/data/plugins/`

4. 通过面板重启bot以加载插件。

如果仍不会部署请参考[AstrBot 官方文档](https://docs.astrbot.app/)。

> 提示：AstrBot 提供**可视化管理面板**与**插件系统**；很多配置可以在 WebUI 中完成。

### 3.3 开发插件（v4）

作为一个成长中的bot，豆子欢迎各位开发者进行pr。

* 在 `plugins/` 下新建独立目录，内含最小化入口与 `pyproject.toml`/`requirements.txt`（如需要）。至少应包含`main.py`和`metadata.yaml`。
* 插件代码应**避免阻塞**，尽量使用异步 I/O；
* 将**密钥**放入环境变量或独立配置文件，不要写死在仓库中。



## 4. 旧版本导读

### 4.1 v3（Mirai）

* 适合复现旧功能或迁移思路；
* 鉴于 Mirai 官方已跑路，不建议再对此版本进行部署；
* MCL 登录目前需要自行签名，或者通过 overflow 对接 NapCat，具体操作不多赘述，请自行搜索；
* mirai-jvm 目录下插件依赖于 mirai-console ，本仓库仅提供`src/main`下主要源码，请自行分辨将各文件放在Mirai插件模板的合适位置，自行打包后投放至 `plugins` 目录；
* lua-mirai 直接基于 mirai-core，具体可见 lua-mirai 官方文档；
* mirai-api-http 基于 OneBot 标准，其插件理论上可通过 http/ws 连接其他支持 OneBot 的框架（如 NapCat）；
* 鉴于 mirai-native 的特殊性，和 mirai-console 部分插件可能发生冲突，上述方案不一定适用。目前经个人测试确定可行的一个方案是通过 MiraiCQ 连 NapCat 的正向 Websocket，合理放置插件的`dll`和`json`位置。`v3_epk_config.json`无法直接导入，请打开插件面板后对照`json`逐条配置。

### 4.2 v2（CQP）

* 酷Q已停运；如需复刻或回溯，请以其他底层作为事件/协议桥接；
* 可参考上方针对`mirai-native`的部署方案进行部署，合理放置插件的`dll`和`json`位置，在插件面板导入`doge-v2.epk`；
* 该目录只包含可以找到的部分源文件，并不能复刻v2豆子全部功能，也缺少相关的本地数据。`v2_epk_config.json`为`doge-v2.epk`解码整理所得，便于查看，无法直接导入。
* 由于生态陈旧，**不建议用户使用 v2**。



## 5. 运行与调试建议

* **最小可运行**：先仅接入一个平台（例如 QQ），验证收发消息，再逐步开启其他平台与功能。
* **日志与排障**：

  * 启动失败：优先检查 Python 版本、依赖安装、端口占用、环境变量；
  * 登录异常：检查平台凭据、风控/设备锁、频率限制；
  * 收发异常：核对适配器开关、路由/权限、消息上报/推送配置。
  * 回复错误：检查文件目录是否对应、部分功能的 API KEY 是否配置



## 6. 常见问答（FAQ）

**Q: 一次性支持多平台吗？**

A: 可以。建议先接一个平台，稳定后再逐步扩展。

**Q: 插件该放哪里？怎么热更新？**

A: 放在 `plugins/`。支持热加载；生产环境建议重启以保证一致性。

**Q: 需要前置驱动或手机协议文件吗？**

A: 取决于所选平台与适配器。请按对应文档准备设备信息、协议选择与风控处理策略。



## 7. 参考与延伸阅读

* [NapCat 官方文档](https://napneko.github.io/guide/napcat)
* [AstrBot 官方文档](https://docs.astrbot.app/)
* [Mirai 官方文档](https://docs.mirai.mamoe.net/)
* [Mirai 插件模板](https://github.com/project-mirai/mirai-console-plugin-template)
* [lua-mirai 官方文档](https://only52607.github.io/lua-mirai/)
* [OneBot 官方文档](https://onebot.dev/)
* [MiraiCQ 项目地址](https://github.com/super1207/MiraiCQ)
* [丽琪bot 仓库地址](https://github.com/fyr233/liqiv3)
* [豆子 Doge 前仓库地址](https://github.com/doge-qbot/doge-repo)

> 若你在使用本导读时发现与仓库实际不符，请提交 Issue 说明具体目录与文件，我们会同步更新本文件。



## 8. 许可证

本仓库使用 **GPL-3.0** 许可证。提交贡献即默认接受相同开源协议。
