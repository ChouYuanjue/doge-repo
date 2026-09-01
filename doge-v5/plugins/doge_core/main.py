from __future__ import annotations

from pathlib import Path

from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from data.plugins.doge_shared.agent_tools import DogeWeatherTool, register_domain_tools
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


@register("doge_core", "runnel", "Doge 核心运行、状态与统计", "5.5.0")
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

    def _adapters(self, event: AstrMessageEvent) -> list[str]:
        try:
            cfg = self.context.get_config(umo=event.unified_msg_origin)
            return [
                f"{p.get('id', '?')}:{p.get('type', '?')}"
                for p in cfg.get("platform", [])
                if p.get("enable", True)
            ]
        except Exception:
            return []

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def count_usage(self, event: AstrMessageEvent):
        # Aggregate only: platform + top-level command + date. No content/user IDs.
        self.counter.record(event.get_platform_name(), event.message_str or "")

    @filter.on_llm_request(priority=100)
    async def onebot_plain_prompt(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
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
        adapters = self._adapters(event)
        lines = [
            f"Doge {v['doge']} · git {v['git']}",
            f"AstrBot {v['astrbot']} · Python {v['python']}",
            f"default profile: {counts['plugins']} plugins · {counts['commands']} commands · {tools} Agent tools",
        ]
        if adapters:
            lines.append("adapters: " + " · ".join(adapters))
        lines.append(
            f"current: {event.get_platform_name()} · instance={event.get_platform_id()}"
        )
        yield text_result(event, "\n".join(lines), markdown=False)

    @filter.command("status")
    async def status(self, event: AstrMessageEvent):
        s = system_snapshot(self.data_root)
        ports = s["ports"]
        adapters = self._adapters(event)
        lines = [
            f"host uptime: {s['host_uptime']} · load {s['load']}",
            f"memory: {s['memory']} ({s['memory_pct']:.1f}%) · AstrBot RSS {s['astrbot_rss']}",
            f"disk: {s['disk']} ({s['disk_pct']:.1f}%)",
            "local links: "
            + f"NapCat 6099={'up' if ports[6099] else 'down'} · "
            + f"OneBot 6199={'up' if ports[6199] else 'down'} · "
            + f"Dashboard 6185={'up' if ports[6185] else 'down'}",
        ]
        if adapters:
            lines.append("configured adapters: " + " · ".join(adapters))
        yield text_result(event, "\n".join(lines), markdown=False)

    @filter.command("statics")
    async def statics(self, event: AstrMessageEvent):
        usage = self.counter.snapshot()
        counts, tools = self._product()
        provider = provider_aggregates(self.data_root / "data_v4.db")
        today = __import__("time").strftime("%Y-%m-%d")
        top = top_counts(usage.get("by_command", {}), 5)
        platforms = top_counts(usage.get("by_platform", {}), 5)
        lines = [
            f"product: {counts['plugins']} default plugins · {counts['commands']} top-level commands · {tools} Agent tools",
            f"usage: {usage.get('messages', 0)} inbound messages · {usage.get('commands', 0)} slash commands · today {usage.get('by_date', {}).get(today, 0)} messages",
            f"LLM: {provider['requests']} requests · {provider['tokens']} tokens ({provider['output_tokens']} output) · avg {provider['avg_latency']:.2f}s",
        ]
        if platforms:
            lines.append("platforms: " + " · ".join(f"{k} {v}" for k, v in platforms))
        if top:
            lines.append("top commands: " + " · ".join(f"/{k} {v}" for k, v in top))
        yield text_result(event, "\n".join(lines), markdown=False)
