# Doge 大表情 / 贴纸后端

本目录由 Doge 主仓库直接维护，来源于 `nagatoquin33/astrbot_plugin_stealer`，基线提交 `f5f51834bb0b9bb01811303c542604f805e0f019`。原始说明保存在 `UPSTREAM_README.md` / `UPSTREAM_README_EN.md`，许可证保持不变。

## 在 Doge 中的职责

这里只提供后端能力：群聊图片自动收集、VLM 分类与标签、语义检索、素材作用域、自动发送、容量维护和 WebUI 数据管理。

它**不注册任何用户命令，也不注册任何 LLM tool**。Doge 的公开边界固定为：

- `/social emoji ...`：已收集 QQ 大表情 / sticker 的管理与自动化；
- `search_emoji` / `send_emoji` / `steal_emoji`：由 `doge_social` 注册给 Agent 的语义工具；
- `/meme ...` / `doge_meme`：固定模板 meme-generator，属于 `doge_memes`，与本后端无关。

不要重新引入 `/meme`、`search_meme`、`send_meme` 或 `steal_meme` 作为本后端的公开接口。内部历史配置字段（例如 `steal_meme`、`meme_chance`）为兼容已有运行数据暂时保留，不代表产品语义。
