# 豆子 Doge v5

Doge v5 是对 v2-v4 的**能力级重构**，运行于 AstrBot 4.27.x / Python 3.12。目标不是把旧目录机械搬过来，而是把仍有价值的行为重新组织成清晰、可测试、可组合的正式插件，同时把无法继续作为生产能力的历史实现放入 Legacy museum。

## 1. 核心结构

v5 分成四层：

1. **正式插件层**：`plugins/doge_*`，每个插件负责一个相对独立的产品域；
2. **共享层**：`plugins/doge_shared`，包含算法、服务封装、presentation、registry、Help renderer、Agent bridge 等，不作为 AstrBot 插件单独加载；
3. **Agent 编排层**：Persona + capability inventory + dedicated tools + generic capability bridge；
4. **历史层**：`doge_legacy` 与 `LEGACY.md`，默认不加载，只用于历史追溯和显式 opt-in。

`plugin_manifest.json` 是哪些插件能够被部署的真值表。`planned` 和 `merged` 项不会被当成独立生产插件物化。

## 2. Capability registry

`plugins/doge_shared/resources/capability_registry.json` 是 v5 公开能力的单一事实源。以下内容都由它派生：

- `/help` 的分层导航；
- `HELP.md`；
- 使用统计中的 canonical capability；
- Agent 的 authoritative capability inventory；
- generic Agent bridge 的可调用白名单；
- Legacy 的帮助和迁移索引。

因此新增或修改公开能力时，不应只在 handler 里写一条新分支；必须同步 registry。

### 参数约定

公开 usage 使用常见 CLI 记法：

```text
<arg>       必填位置参数
[arg]       可选位置参数
{a|b}       必须从候选中选一个
[{a|b}]     可选枚举项
[arg ...]   可重复可选参数
```

不要再使用无法说明内容的 `[...]` 万能占位符。图片、CIF/mCIF 等非文本输入使用 registry 的 `inputs` 字段描述，在 Help 中单独显示，不混进位置参数。

`tests/test_parameter_semantics.py` 会检查这些约束，避免后续新增功能重新退回含糊写法。

## 3. Help

`/help` 默认使用专用 Typst renderer 生成本地图片卡片；它不是通用 `/md` 模板的截图，而是一套独立的 Doge Help UI：深色背景、终端式 Quick Start、命令/必填/可选参数的语义着色，以及针对 root dashboard 的紧凑布局。

Help 可以按群/会话切换显示方式：

```text
/help style image
/help style text
```

偏好是隔离保存的，默认 `image`。如果图片渲染失败，只对本次响应回退文字，不会偷偷修改用户偏好。

## 4. Agent 编排

Persona 的 `tools=null` 表示 AstrBot 默认允许当前已注册的全部活动 Tools。为了不为近两百个叶子能力重复注册近两百份 schema，Doge 使用两条路径：

- 高频域保留 dedicated domain tool；
- 其他正式能力通过 `doge_capability` 调用完整 canonical command。

`doge_capability` 只接受 capability registry 中的正式非 Legacy 指令，并复用**真实 command handler**，不复制第二套业务实现。

Agent 位于插件结果之上：可以组合多个工具的文本结果、去重、比较和压缩，只展示对问题最有价值的内容。若用户需要原始插件输出，Agent 可以在合适时给出完整直接命令，但不应每次机械追加。

### 富媒体延迟展示

AstrBot 的默认 local tool 行为会把 `MessageEventResult` 中的图片直接发给用户。为了让 Agent 真正拥有取舍权，generic bridge 会先捕获插件图片并转成短期 asset id；只有 Agent 决定图片有价值时才调用 `doge_present` 展示选中的资产。

图片临时资产只在当前事件生命周期内有效。文件等复杂富媒体默认不被自动二次上传；需要完整原始文件时，应使用直接命令。

## 5. 群级模块热插拔

AstrBot 4.27.x 已经原生提供 session-level plugin manager，并通过 `session_plugin_config` 维护 `enabled_plugins / disabled_plugins`。Doge 不再自造第二套模块数据库，只提供一个很薄的群管理命令外壳：

```text
/admin modules list
/admin modules off games
/admin modules on games
/admin modules reset
```

修改权限按当前群的真实 owner/admin 信息判断。`doge_core` 与 `doge_admin` 是恢复入口，锁定不可关闭；`doge_legacy` 不属于正式热插拔模块。

AstrBot 原生 manager 会过滤普通 command handler；`doge_shared.module_control` 额外把同一状态应用到 Agent domain tools，并让 generic capability bridge 在调用目标 handler 前再次检查模块状态。

## 6. Persona 与 transient affect

生产 Persona 在 `persona/doge.json`。豆子的自我认知是寄居于服务器、模型和工具链之间的赛博生命；表达风格以灰原哀为唯一角色参考，但不声称自己就是该角色，也不继承原作世界观。

`plugins/doge_shared/affect.py` 提供短期、内存级、会衰减的 valence/arousal 状态。它允许语气和主动性随明确的赞扬、冒犯、道歉等互动轻微变化，但不能改变事实标准、工具权限、安全边界或任务完成质量。

完整说明见 `PERSONA.md`。

## 7. 正式能力域

### Math 与 Lab 的边界

`/math` 是**计算/求解层**：基础算术、高精度数值、SymPy 符号化简/展开/因式分解、方程、微积分、数论、统计、OEIS、Wolfram|Alpha，以及 Lean / Coq(Rocq) / Rzk 的轻量 playground bridge。形式化入口只负责 starter/源码转交，不在没有真实 proof kernel 的情况下宣称证明通过。

`/lab` 是**可视化/模拟层**：分形、动力系统、统计物理、元胞自动机、几何/物理教学图等。它的目标是让机制“看得见”，不是充当通用 CAS。Conway Life 保留历史功能语义，输出真实 GIF 演化动画。

RRPL 也按同样原则从“一个 renderer”升级为可理解能力：`/lang rrpl syntax` 给出 0–8 米格笔画、`-` 左右 packing、`|` 上下 packing、括号和汉字引用规则；`/lang rrpl explain` 可在 render 前展开引用并检查结构。

当前默认 profile 包括：

- `doge_core`：Help、版本、状态、统计、Agent foundation；
- `doge_admin`：AstrBot 框架命令与群模块开关；
- `doge_math` / `doge_ai` / `doge_cs` / `doge_code`；
- `doge_typeset` / `doge_diagrams` / `doge_playground` / `doge_engineering`；
- `doge_papers` / `doge_bio` / `doge_chem` / `doge_materials` / `doge_astro` / `doge_clinical`；
- `doge_linguistics`；
- `doge_games` / `doge_alchemy` / `doge_arena`；
- `doge_media` / `doge_misc` / `doge_lookup`。

以 `plugin_manifest.json` 为最终准绳，不要根据目录名猜生产加载状态。

## 8. 部署

先 dry-run：

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins \
  --profile default \
  --dry-run
```

确认后物化正式 profile：

```bash
python3.12 doge-v5/tools/materialize_plugins.py \
  --dest /path/to/AstrBot/data/plugins \
  --profile default \
  --mode symlink \
  --force
```

安装 Persona 与 runtime command policy：

```bash
python3 doge-v5/tools/install_runtime_profile.py --runtime /path/to/AstrBot
```

生产修改前应先备份 runtime 配置和数据库。若只修改 AstrBot 插件，通常不需要停止 NapCat；只重启 AstrBot 即可。

## 9. 测试

生产环境应使用 AstrBot 自己的 Python 解释器执行测试，以避免“系统 Python 能 import、生产 Python 缺依赖”的假绿：

```bash
/root/.local/share/uv/tools/astrbot/bin/python -m unittest discover \
  -s doge-v5/tests \
  -p 'test_*.py'
```

提交前至少还应执行：

```bash
git diff --check
```

并确认没有把凭据、token、runtime 私有配置或临时渲染文件提交进仓库。

## 10. 文档与历史

- `HELP.md`：由 registry 生成的正式功能帮助；
- `LEGACY.md`：v2-v4 历史功能与迁移状态；
- `PERSONA.md`：生产人格与短期情绪边界；
- `PLUGIN_ARCHITECTURE.md`：插件职责与迁移架构；
- `TRUTHFULNESS.md`：真实结果 / fallback 策略；
- `THIRD_PARTY.md`：第三方代码、依赖和许可证边界；
- `feature_catalog.json` / `FEATURE_MATRIX.md`：历史产品审计；
- `legacy_coverage.json`：机器可读的旧功能 containment map。

v5 的基本原则很简单：**正式能力尽量真实、可复验、可组合；历史能力尽量可追溯；Help、Agent 和统计尽量只维护一份真相。**
