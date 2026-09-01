# Doge v5 Typesetting

Doge v5 把历史的 `v3/tex`、`v4/latex`、`v4/utex` 与 `v4/typst` 重新整理成两个稳定入口：`/tex` 负责 TeX 数学/图形排版，`/typst` 负责 Typst 公式、卡片和完整文档。两者都直接从 `event.message_str` 提取命令后的原始 payload，不依赖 AstrBot 按空格自动拆参，因此换行、空格、逗号和代码块不会被破坏。

## `/tex`

### 命令

- `/tex <LaTeX>`：smart 模式。优先原生 TeX；原生后端不可用时，简单公式回退本地 MathText。
- `/tex native <LaTeX>`：强制原生 TeX，适合 `align`、matrix、TikZ 等完整环境。
- `/tex local <LaTeX>`：只使用本机 MathText；适合隐私敏感或断网场景。
- `/latex`：兼容 `/tex` smart。
- `/utex`：兼容 `/tex native`。

### 原生 TeX 后端

当前优先复用 UpMath 的 TeX 后端，但不沿用 v4 `requests + CairoSVG` 的实现：

1. 输入使用 raw DEFLATE + URL-safe Base64 的压缩路径，长公式/TikZ 不会把 URL 膨胀到不可控；
2. 使用 AstrBot runtime 已有的 `aiohttp`，显式总超时、连接超时和一次重试；
3. 先取 SVG，检查 `0×0 SVG` 这类“HTTP 200 但实际编译失败”的情况；
4. 如果运行环境有 `resvg_py` 或可工作的 CairoSVG，则从 SVG 高质量栅格化；否则直接使用 UpMath PNG，并通过 Pillow 做白边和放大处理；
5. smart 模式只在原生后端失败后尝试 MathText fallback，不会把 TikZ/完整 TeX 静默降级成错误结果。

注意：默认原生模式会把公式发送到外部 TeX 服务。需要本地处理时使用 `/tex local`。

### 已验证输入

- 普通公式：`E=mc^2`
- 同一公式中的多个逗号：不再拆行
- `align*`
- `pmatrix`
- TikZ
- 多行本地 MathText
- 错误宏/未闭合输入：返回错误而不是空图

## `/typst`

### 命令

- `/typst math <formula>`：自动宽高的数学公式。
- `/typst card <markup>`：默认群聊卡片；页面高度自动增长。
- `/typst doc <full source>`：完整 Typst 源码，最多向群聊发送 4 页 PNG。
- `/typst chat <markup>`：轻量内置聊天卡片，可写 `#yau[...]`。
- `/tym` → `math`；`/typ` → `doc`；`/yau` → `chat`。

v5 使用 `typst-py >=0.15,<0.16`，不再依赖旧 `@preview/ourchat:0.2.0` 模板包。Typst package cache 放在 Doge 数据目录下，完整文档仍可以使用 Typst 官方 package 机制。

### 中文/CJK 字体

Typst 可以正常编译一个缺字字体环境，却可能把中文画成方块。v5 不接受这种静默失败：

- 输入包含 CJK 字符时先检查系统/显式字体目录；
- 没有 CJK 字体则直接返回可读错误；
- 推荐在 AstrBot runtime 中安装 Noto CJK / Source Han；
- 也可以设置 `DOGE_TYPST_FONT_PATHS=/path/to/fonts[:/another/path]`；
- v5 仓库不内置或分发字体文件。

### 资源限制

- Typst source：最多 30,000 字符；
- PNG：96–360 PPI；默认 220；
- 完整文档：最多 4 页；
- TeX source：最多 12,000 字符；
- 所有图片发送后由命令层清理临时输出。

## 依赖

排版依赖单独放在 `plugin/requirements-typeset.txt`，避免把科学绘图的重依赖与核心逻辑混成一组。生产运行建议 Python 3.12+。

## 迁移决策

`feature_catalog.json` 中 `tex` 与 `typst` 都标记为 `native-v5`。materializer 不再默认部署旧 `doge_latex`、`doge_utex`、`doge_typst`，避免同一 AstrBot 实例重复注册 `/tex`、`/latex`、`/typ` 等命令。
