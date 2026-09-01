# Result truthfulness policy

Doge 的正式功能允许“模拟”和“虚构”，但不允许把它们伪装成现实数据。

- 查询类：只返回真实后端/真实镜像的数据；后端失败时可以换另一个明确标注的真实来源，不能塞示例数据。
- 执行类：必须真实执行或明确失败；未知协议响应不能冒充执行结果。
- 翻译/字典类：未覆盖内容必须暴露 unknown/sealed/hybrid provenance，不能把可逆编码或模糊候选说成词典翻译。
- 模拟/算法类：RNG、Monte Carlo、Q-learning 等本来就是实验过程，可以使用随机数，但界面必须表现为实验/模拟而不是现实观测。
- 生成类：`/fuse` 是群聊虚构设定；Arena 的 LLM 只负责叙事裁决，卡牌事实来自保存的数据。两者都不得包装成现实知识。
- 平台动作：只有真正调用平台 API 成功后才能声称动作完成。
- Renderer：只声称“把输入渲染出来”，不把图形解释成额外事实。

`truthfulness_policy.json` 必须覆盖 default profile 的每个插件；`tools/audit_live_backends.py` 用真实网络周期性检查主要 grounded 后端。
