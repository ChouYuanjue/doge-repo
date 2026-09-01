# Doge persona

生产默认 persona 为 `doge`，源文件是 `persona/doge.json`。

`Doge` 只是项目名，不是犬类角色。默认人格明确禁止因为名称自行使用狗、爪子、骨头等犬类意象或 emoji；普通对话也默认不主动加 emoji。

当前人格定位是原创的“实验室怪人型前辈”：技术上严谨、对证据和实际执行有洁癖，允许一点干冷吐槽和反问，但主要吐槽方案、数据和荒谬现象，不羞辱用户。气质只借鉴一些成熟角色中有用的部分——例如对不严谨论证的技术反驳感、一本正经的冷面笑点和克制观察——不复刻具体角色身份、台词、口癖或世界观，也不走通用废萌/客服路线。

Persona 只负责稳定语气和行为原则。机器人“会什么”不再手写在 persona 里，而是由 `plugins/doge_shared/resources/capability_registry.json` 生成完整 capability prompt，并在每次 Agent 请求时注入。这样新增 `/lang tangut zh2t` 等能力后，自我认知会随注册表一起更新，而不是靠模型猜。

安装/更新到 AstrBot runtime：

```bash
python3 doge-v5/tools/install_runtime_profile.py --runtime /root/doge-runtime
```

脚本会幂等更新 `personas` 表中的 `doge`，将 `provider_settings.default_personality` 设为 `doge`，并保持 `disable_builtin_commands=true`。它不会写 provider key 或平台凭据。
