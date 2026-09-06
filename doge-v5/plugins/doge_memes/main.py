from __future__ import annotations

from contextlib import contextmanager

import astrbot.api.message_components as Comp
from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, register

from data.plugins.doge_shared.agent_tools import DogeMemeTool, register_domain_tools
from data.plugins.doge_shared.help_service import format_cli_error
from data.plugins.doge_shared.presentation import text_result
from data.plugins.doge_shared.raw_command import command_payload

HELP = """Doge Meme /meme
  /meme <模板关键词> [文字]    生成表情；支持当前/引用图片与 @ 用户头像
  /meme make <模板> [文字]    同上，显式生成
  /meme list [页码]           v4 风格模板列表
  /meme detail <模板>         模板参数、别名与预览
  /meme off <模板>            禁用单个模板（Bot 管理员）
  /meme on <模板>             重新启用模板（Bot 管理员）
  /meme blist                 查看禁用模板（Bot 管理员）
  /meme status                上游引擎与模板状态
  /meme resources             资源下载/初始化状态
底层直接复用生产中的 astrbot_plugin_meme_generator；不另造模板引擎。"""


@register("doge_memes", "runnel", "模板 meme 正式入口：自动解析可取得的图片与 QQ 头像素材", "1.0.2")
class DogeMemes(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self.context = context
        register_domain_tools(context, "doge_memes", DogeMemeTool())

    def _engine(self):
        meta = self.context.get_registered_star("astrbot_plugin_meme_generator")
        engine = getattr(meta, "star_cls", None) if meta else None
        if engine is None:
            raise RuntimeError("meme-generator 上游未加载")
        return engine

    @staticmethod
    def _require_bot_admin(event: AstrMessageEvent) -> None:
        if not event.is_admin():
            raise PermissionError("只有 Bot 管理员可以修改 meme 模板开关")

    @contextmanager
    def _generation_event(self, event: AstrMessageEvent, payload: str):
        """Present explicit /meme payload to the v4-lineage engine, then restore event."""
        engine = self._engine()
        raw = payload.strip()
        prefix = str(getattr(getattr(engine, "meme_config", None), "trigger_prefix", "") or "")
        if prefix:
            first, sep, tail = raw.partition(" ")
            raw = f"{prefix}{first}{sep}{tail}"
        old_message = event.message_str
        plains = [seg for seg in event.get_messages() if isinstance(seg, Comp.Plain)]
        old_plain = [seg.text for seg in plains]
        event.message_str = raw
        if plains:
            plains[0].text = raw
            for seg in plains[1:]:
                seg.text = ""
        try:
            yield engine
        finally:
            event.message_str = old_message
            for seg, text in zip(plains, old_plain):
                seg.text = text

    async def _generate(self, event: AstrMessageEvent, payload: str):
        if not payload.strip():
            raise ValueError("用法：/meme <模板关键词> [文字参数]")
        with self._generation_event(event, payload) as engine:
            cfg = getattr(engine, "meme_config", None)
            if cfg is not None and not cfg.is_plugin_enabled():
                raise RuntimeError("meme-generator 当前被管理员全局禁用")
            data = await engine.meme_manager.generate_meme(event)
        if not data:
            raise ValueError("没有匹配到模板、模板已禁用，或当前仍在冷却")
        result = event.chain_result([Comp.Image.fromBytes(data)])
        result.use_markdown(False)
        return result

    async def _relay(self, iterator):
        async for item in iterator:
            yield item

    @filter.command("meme")
    async def meme(self, event: AstrMessageEvent):
        try:
            payload = command_payload(event.message_str, "meme").strip()
            if not payload or payload.casefold() in {"help", "?"}:
                yield text_result(event, HELP, markdown=False)
                return
            action, sep, rest = payload.partition(" ")
            low = action.casefold()
            rest = rest.strip() if sep else ""
            engine = self._engine()

            if low in {"make", "gen", "generate"}:
                yield await self._generate(event, rest)
                return
            if low in {"list", "ls"}:
                page = 1
                if rest:
                    if not rest.isdigit():
                        raise ValueError("用法：/meme list [页码]")
                    page = int(rest)
                async for item in engine.template_list(event, page):
                    yield item
                return
            if low in {"detail", "info"}:
                if not rest:
                    raise ValueError("用法：/meme detail <模板关键词>")
                async for item in engine.template_info(event, rest):
                    yield item
                return
            if low == "off":
                self._require_bot_admin(event)
                if not rest:
                    raise ValueError("用法：/meme off <模板关键词>")
                async for item in engine.disable_template(event, rest):
                    yield item
                return
            if low == "on":
                self._require_bot_admin(event)
                if not rest:
                    raise ValueError("用法：/meme on <模板关键词>")
                async for item in engine.enable_template(event, rest):
                    yield item
                return
            if low in {"blist", "disabled"}:
                self._require_bot_admin(event)
                async for item in engine.list_disabled(event):
                    yield item
                return
            if low in {"resources", "resource"}:
                self._require_bot_admin(event)
                async for item in engine.resource_status(event):
                    yield item
                return
            if low == "status":
                self._require_bot_admin(event)
                async for item in engine.plugin_info(event):
                    yield item
                return

            # v4's essence: a meme keyword plus its image/text/@ parameters.
            yield await self._generate(event, payload)
        except Exception as exc:
            logger.warning("doge meme failed: %s: %s", type(exc).__name__, exc)
            yield text_result(event, format_cli_error("meme", exc), markdown=False)
