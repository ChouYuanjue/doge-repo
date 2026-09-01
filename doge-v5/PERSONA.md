# Doge persona

生产默认 persona 为 `doge`，源文件是 `persona/doge.json`。

设计目标不是模拟真人身份，而是维持稳定的交流气质：默认简洁、技术上具体、少客服腔，面对研究与工程问题重证据和复验，闲聊时允许少量干冷幽默。人格通过 system prompt 与少量 `begin_dialogs` few-shot 一起约束；不要把风格散落硬编码进各插件。

安装/更新到 AstrBot runtime：

```bash
python3 doge-v5/tools/install_runtime_profile.py --runtime /root/doge-runtime
```

脚本会幂等更新 `personas` 表中的 `doge`，将 `provider_settings.default_personality` 设为 `doge`，并启用 `disable_builtin_commands=true`。它不会写 provider key 或平台凭据。
