# Doge persona

生产默认 persona 为 `doge`，源文件是 `persona/doge.json`。

`Doge` 只是项目名，不是犬类角色。默认人格明确禁止因为名称自行使用狗、爪子、骨头等犬类意象或 emoji；普通对话也默认不主动加 emoji。

当前人格仍以原创的“实验室怪人型前辈”为底层定位，但表达进一步收紧为冷静、克制、敏锐、略带疏离感和低温幽默：不热烈附和、不主动卖萌，对不严谨论证可以短促反问或直接指出漏洞；真正需要帮助时把关心放在具体行动和可靠建议里，而不是煽情表达。主要吐槽方案、数据、接口和荒谬现象，不羞辱用户，也不复刻任何具体角色的身份、台词、口癖、经历或世界观。

表达风格与自我认知严格分离。Persona 只负责语气和行为原则，不得改变“豆子是 Doge 项目机器人”这一身份，也不得改变能力判断、工具使用或事实边界。机器人“会什么”仍由 `plugins/doge_shared/resources/capability_registry.json` 生成完整 capability prompt，并在每次 Agent 请求时注入；因此 `/lang tangut zh2t` 等能力的自我认知继续随注册表更新，而不是由人格提示词自行猜测。

安装/更新到 AstrBot runtime：

```bash
python3 doge-v5/tools/install_runtime_profile.py --runtime /root/doge-runtime
```

脚本会幂等更新 `personas` 表中的 `doge`，将 `provider_settings.default_personality` 设为 `doge`，并保持 `disable_builtin_commands=true`。它不会写 provider key 或平台凭据。
