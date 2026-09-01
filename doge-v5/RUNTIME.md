# Runtime 选择

- AstrBot: 4.27.x（审计时 HEAD 4.27.4）
- Python: >=3.12
- QQ: NapCat -> OneBot WebSocket -> AstrBot aiocqhttp
- Agent: AstrBot built-in Agent Runner
- Tool API: `FunctionTool` + `Context.add_llm_tools()`
- Skills: 可用于组合任务说明
- SubAgent: 后续可选；不作为 v5 核心依赖
- Computer Use: Agent 需要执行代码/文件操作时优先 sandbox；不要给普通群用户 local host 权限

本目录没有 systemd/docker-compose 启动文件是有意的：本轮不应该碰 alibaba-server-10 上现有 Nginx、Docker 或端口。真正部署时应创建独立 AstrBot runtime，再由 `tools/materialize_plugins.py` 把 v5 所需插件物化进去。
