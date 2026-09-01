from __future__ import annotations

from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import LLMResponse, ProviderRequest
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.utils.astrbot_path import get_astrbot_data_path

from data.plugins.doge_shared.agent_bridge import DogeCapabilityTool, DogePresentTool
from data.plugins.doge_shared.agent_tools import DogeWeatherTool, register_domain_tools
from data.plugins.doge_shared.affect import TransientAffect
from data.plugins.doge_shared.capabilities import agent_capability_prompt, capability_display
from data.plugins.doge_shared.help_live import (
    HelpPreferenceStore,
    normalize_help_style_topic,
    render_help_card,
    render_help_live,
    scope_key,
)
from data.plugins.doge_shared.module_control import disabled_plugins, filter_toolset_for_session
from data.plugins.doge_shared.persona_runtime import PersonaRuntime
from data.plugins.doge_shared.presentation import image_result, markdown_to_plain, text_result
from data.plugins.doge_shared.release import DOGE_VERSION
from data.plugins.doge_shared.raw_command import command_payload
from data.plugins.doge_shared.runtime_stats import (
    UsageCounter,
    product_counts,
    provider_aggregates,
    system_snapshot,
    top_counts,
    version_snapshot,
)


@register("doge_core", "runnel", "Doge 核心运行、状态与统计", DOGE_VERSION)
class DogeCore(Star):
    """Always-on Doge foundation: identity, health, statistics and Agent basics."""

    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        self.v5_root = Path(__file__).resolve().parents[2]
        self.repo_root = self.v5_root.parent
        self.data_root = Path(get_astrbot_data_path())
        self.core_data_dir = Path(StarTools.get_data_dir("doge_core"))
        self.counter = UsageCounter(
            self.core_data_dir / "usage.json",
            self.data_root / "logs",
        )
        self.help_preferences = HelpPreferenceStore(self.core_data_dir / "help_preferences.json")
        self.affect = TransientAffect()
        self.persona_runtime = PersonaRuntime(self.affect)
        register_domain_tools(
            context,
            "doge_core",
            DogeWeatherTool(),
            DogeCapabilityTool(),
            DogePresentTool(),
        )

    def _product(self) -> tuple[dict[str, int], int]:
        counts = product_counts(self.v5_root)
        try:
            tools = len(self.context.get_llm_tool_manager().func_list)
        except Exception:
            tools = 0
        return counts, tools

    def _help_scope(self, event: AstrMessageEvent) -> tuple[str, str]:
        try:
            group_id = event.get_group_id()
        except Exception:
            group_id = None
        try:
            platform = event.get_platform_name()
        except Exception:
            platform = "unknown"
        return scope_key(str(platform or "unknown"), str(group_id) if group_id else None, event.unified_msg_origin)

    @filter.event_message_type(filter.EventMessageType.ALL, priority=10000)
    async def count_usage(self, event: AstrMessageEvent):
        # Aggregate only: platform/date + registry-recognized invocation. No content/user IDs.
        self.counter.record(event.get_platform_name(), event.message_str or "")

    @filter.on_llm_request(priority=100)
    async def enrich_llm_request(self, event: AstrMessageEvent, req: ProviderRequest) -> None:
        # Persona owns voice; the registry owns capability truth.  The generic
        # bridge makes every formal non-Legacy command reachable without adding
        # 199 near-duplicate tool schemas to each request.
        try:
            sender = str(event.get_sender_id() or "")
        except Exception:
            sender = ""
        # Affect is relationship-local rather than group-global: one person's
        # bad turn should not make Doge inexplicably cold to everyone else.
        affect_scope = event.unified_msg_origin + (f"|sender:{sender}" if sender else "")
        mood = self.affect.observe(affect_scope, event.message_str or "")
        await filter_toolset_for_session(event.unified_msg_origin, req.func_tool)
        session_disabled = await disabled_plugins(event.unified_msg_origin)
        req.system_prompt = (
            (req.system_prompt or "")
            + "\n\n"
            + agent_capability_prompt()
            + "\n\n"
            + self.affect.prompt(mood)
            + "\n\n"
            + self.persona_runtime.prompt(affect_scope, event.message_str or "", mood)
        )
        if session_disabled:
            req.system_prompt += (
                "\n\n# Current session modules\n"
                "The following Doge modules are disabled for this group/session: "
                + ", ".join(x.removeprefix("doge_") for x in sorted(session_disabled))
                + ". Do not use or claim those modules are currently callable until a group administrator re-enables them."
            )
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

    @filter.on_decorating_result(priority=100)
    async def transport_markdown_result(self, event: AstrMessageEvent) -> None:
        """Keep formatting transport-specific at the final outbound boundary.

        Normal LLM replies are created by AstrBot itself rather than through
        Doge's ``text_result`` helper, so their Markdown flag must be restored
        explicitly for QQ Official.  OneBot/NapCat is always plain text.  Only
        LLM results are forced to Markdown on QQ Official so media/plugin
        results that intentionally disabled Markdown remain untouched.
        """
        result = event.get_result()
        if result is None:
            return
        platform = str(event.get_platform_name() or "").lower()
        if platform == "aiocqhttp":
            result.use_markdown(False)
        elif platform == "qq_official" and result.is_llm_result():
            result.use_markdown(True)

    @filter.command("help")
    async def help(self, event: AstrMessageEvent):
        topic = command_payload(event.message_str, "help")
        pref_action = normalize_help_style_topic(topic)
        pref_key, pref_label = self._help_scope(event)
        if pref_action is not None:
            action, value = pref_action
            if action == "query":
                current = self.help_preferences.get(pref_key)
                yield text_result(
                    event,
                    f"Help 显示：{'图片' if current == 'image' else '文字'}（{pref_label}）\n"
                    "/help style image\n/help style text",
                    markdown=False,
                )
                return
            if action == "invalid":
                yield text_result(
                    event,
                    "Help 样式只支持 image / text。\n/help style image\n/help style text",
                    markdown=False,
                )
                return
            assert value is not None
            mode = self.help_preferences.set(pref_key, value)
            yield text_result(
                event,
                f"Help 已切换为{'图片' if mode == 'image' else '文字'}显示（{pref_label}）。",
                markdown=False,
            )
            return

        text, markdown = render_help_live(topic)
        if self.help_preferences.get(pref_key) == "text":
            yield text_result(event, text, markdown=markdown)
            return

        path: Path | None = None
        try:
            path = render_help_card(self.core_data_dir, text)
            yield image_result(event, path)
        except Exception as exc:
            logger.warning(f"doge help card render failed; falling back to text: {exc}")
            yield text_result(event, text + "\n\n[图片排版失败，本次已回退到文字。]", markdown=False)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

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
