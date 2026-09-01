from __future__ import annotations

from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from data.plugins.doge_shared.agent_tools import DogeWeatherTool, register_domain_tools
from data.plugins.doge_shared.capabilities import agent_capability_prompt, capability_display
from data.plugins.doge_shared.help_service import render_help
from data.plugins.doge_shared.presentation import markdown_to_plain, text_result
from data.plugins.doge_shared.raw_command import command_payload
from data.plugins.doge_shared.runtime_stats import (
    UsageCounter,
    product_counts,
    provider_aggregates,
    system_snapshot,
    top_counts,
    version_snapshot,
)


@register("doge_core", "runnel", "Doge 核心运行、状态与统计", "5.7.0")
class DogeCore(Star):
    """Always-on Doge foundation: identity, health, statistics and Agent basics."""

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.v5_root = Path(__file__).resolve().parents[2]
        self.repo_root = self.v5_root.parent
        self.data_root = Path(get_astrbot_data_path())
        self.counter = UsageCounter(
            Path(StarTools.get_data_dir("doge_core")) / "usage.json",
            self.data_root / "logs",
        )
        register_domain_tools(context, "doge_core", DogeWeatherTool())

    def _product(self) -> tuple[dict[str, int], int]:
        counts = product_counts(self.v5_root)
        try:
            tools = len(self.context.get_llm_tool_manager().func_list)
        except Exception:
            tools = 0
        return counts, tools


    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def count_usage(self, event: AstrMessageEvent):
        # Aggregate only: platform/date + registry-recognized invocation. No content/user IDs.
        self.counter.record(event.get_platform_name(), event.message_str or "")

    @filter.on_llm_request(priority=100)
    async def enrich_llm_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        # Capability knowledge is generated from the same leaf-level registry as
        # /help and /statics, so the persona cannot drift into "I cannot do X"
        # while X is actually installed.
        req.system_prompt = (req.system_prompt or "") + "\n\n" + agent_capability_prompt()
        if str(event.get_platform_name() or "").lower() != "aiocqhttp":
            return
        req.system_prompt += (
            "\n\n# Transport formatting\n"
            "The current QQ transport is OneBot/NapCat and does not render Markdown. "
            "Write the final user-visible reply as plain text only: no Markdown headings, "
            "bold/italic markers, backticks or fenced code, Markdown tables, or Markdown links. "
            "Use ordinary punctuation and plain numbered or bullet-like lines when structure is needed."
        )

    @filter.on_llm_response(priority=100)
    async def onebot_plain_response(self, event: AstrMessageEvent, response: LLMResponse) -> None:
        if str(event.get_platform_name() or "").lower() != "aiocqhttp":
            return
        text = response.completion_text or ""
        if text:
            response.completion_text = markdown_to_plain(text)

    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        topic = command_payload(event.message_str, "help")
        text, markdown = render_help(topic)
        yield text_result(event, text, markdown=markdown)

    @filter.command("ver")
    async def version(self, event: AstrMessageEvent):
        v = version_snapshot(self.repo_root)
        counts, tools = self._product()
        lines = [
            f"Doge {v['doge']}",
            f"Git {v['git']}",
            f"AstrBot {v['astrbot']}",
            f"Python {v['python']}",
            f"默认插件 {counts['plugins']}",
            f"顶层指令 {counts['commands']}",
            f"正式叶子功能 {counts['functions']}",
            f"正式调用形式 {counts['forms']}",
            f"Legacy 历史叶子 {counts['legacy_functions']}",
            f"Agent Tools {tools}",
        ]
        yield text_result(event, "\n".join(lines), markdown=False)

    @filter.command("status")
    async def status(self, event: AstrMessageEvent):
        s = system_snapshot(self.data_root)
        ports = s["ports"]
        lines = [
            f"Host uptime {s['host_uptime']}",
            f"Load {s['load']}",
            f"Memory {s['memory']} ({s['memory_pct']:.1f}%)",
            f"AstrBot RSS {s['astrbot_rss']}",
            f"Disk {s['disk']} ({s['disk_pct']:.1f}%)",
            "",
            f"NapCat WebUI 6099 {'UP' if ports[6099] else 'DOWN'}",
            f"OneBot WS 6199 {'UP' if ports[6199] else 'DOWN'}",
            f"AstrBot WebUI 6185 {'UP' if ports[6185] else 'DOWN'}",
        ]
        yield text_result(event, "\n".join(lines), markdown=False)

    @filter.command("statics")
    async def statics(self, event: AstrMessageEvent):
        usage = self.counter.snapshot()
        counts, tools = self._product()
        provider = provider_aggregates(self.data_root / "data_v4.db")
        today = __import__("time").strftime("%Y-%m-%d")
        top = top_counts(usage.get("by_capability", {}), 7)
        lines = [
            "Doge Statics",
            "",
            "产品",
            f"  默认插件 {counts['plugins']}",
            f"  顶层指令 {counts['commands']}",
            f"  正式叶子功能 {counts['functions']}",
            f"  正式调用形式 {counts['forms']}（含 {counts['aliases']} 个兼容别名）",
            f"  Legacy 历史入口 {counts['legacy_commands']}",
            f"  Legacy 历史叶子 {counts['legacy_functions']}",
            f"  历史收容 v2 {counts['history_v2']}/108",
            f"  历史收容 v3 {counts['history_v3']}/34",
            f"  历史收容 v4 {counts['history_v4']}/35",
            f"  Agent Tools {tools}",
            "",
            "使用",
            f"  入站消息 {usage.get('messages', 0)}",
            f"  有效功能调用 {usage.get('commands', 0)}",
            f"  今日消息 {usage.get('by_date', {}).get(today, 0)}",
            "",
            "LLM",
            f"  请求 {provider['requests']}",
            f"  Token {provider['tokens']}",
            f"  输出 Token {provider['output_tokens']}",
            f"  平均延迟 {provider['avg_latency']:.2f}s",
        ]
        if top:
            lines += ["", "Top 功能"]
            lines.extend(f"  {capability_display(k)}  {v}" for k, v in top)
        yield text_result(event, "\n".join(lines), markdown=False)
