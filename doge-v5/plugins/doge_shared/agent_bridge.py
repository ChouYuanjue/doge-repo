from __future__ import annotations

import asyncio
import inspect
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot import logger
from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import File, Image, Music, Plain
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry

from .capabilities import match_invocation, operation_by_id, operations_for_prefix, search_capabilities
from .module_control import is_plugin_enabled

_ASSET_KEY = "_doge_agent_assets"
_MAX_TOOL_TEXT = 18000
_PRESENT_ACK_WAIT_S = 1.5
_DETACHED_SEND_TASKS: set[asyncio.Task] = set()


def _normalize_command(command: str) -> str:
    text = " ".join(str(command or "").strip().split())
    if not text:
        raise ValueError("command 不能为空")
    return text if text.startswith("/") else "/" + text


def _likely_help(command: str) -> str:
    body = command.lstrip("/").strip()
    toks = body.split()
    for n in range(len(toks), 0, -1):
        prefix = " ".join(toks[:n])
        if operations_for_prefix(prefix):
            return f"/help {prefix}"
    return "/help"


def _track_detached_send(task: asyncio.Task) -> None:
    """Keep a transport send alive after the Agent stops waiting for its ACK."""
    _DETACHED_SEND_TASKS.add(task)

    def _done(done: asyncio.Task) -> None:
        _DETACHED_SEND_TASKS.discard(done)
        try:
            done.result()
        except asyncio.CancelledError:
            logger.debug("Detached Doge presentation send was cancelled.")
        except Exception as exc:
            # NapCat may report retcode=1200 after QQ has already accepted and
            # displayed the message.  Never retry here: duplicate rich media is
            # worse than an ambiguous acknowledgement.
            logger.warning(
                "Detached Doge presentation send finished without ACK: %s: %s",
                type(exc).__name__,
                exc,
            )

    task.add_done_callback(_done)


async def _send_presentation_bounded(event, chain: list, *, ack_wait_s: float | None = None) -> str:
    """Send rich media without binding the Agent lifetime to NapCat's ACK.

    QQ/NapCat can display an image immediately yet fail to acknowledge the OneBot
    action until its ~10s transport timeout.  Start the real event.send task, wait
    briefly for normal fast acknowledgements, then leave only that same task running
    in the background.  We deliberately do not retry on timeout because production
    evidence shows the original message may already be visible to the user.
    """
    result = MessageEventResult(chain=list(chain))
    result.use_markdown(False)
    message = MessageChain(chain=result.chain, type="tool_direct_result")
    task = asyncio.create_task(event.send(message), name="doge-present-send")
    _track_detached_send(task)
    wait_s = _PRESENT_ACK_WAIT_S if ack_wait_s is None else max(0.0, float(ack_wait_s))
    if wait_s <= 0:
        return "Presentation dispatched directly to the user; transport acknowledgement is pending. Do not resend it."
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=wait_s)
        return "Presentation sent directly to the user. Do not resend it."
    except asyncio.TimeoutError:
        return "Presentation dispatched directly to the user; transport acknowledgement is pending. Do not resend it."
    except Exception:
        # A quick, unambiguous transport failure should still fail the tool.
        # Only the slow ACK path is detached.
        raise


async def _capture_image(event, comp: Image, asset_root: Path, assets: dict) -> str:
    asset_id = "img-" + uuid.uuid4().hex[:10]
    record: dict[str, str] = {"kind": "image"}
    source_url = str(getattr(comp, "url", "") or getattr(comp, "file", "") or "")
    local = str(getattr(comp, "path", "") or "")
    if local and Path(local).exists():
        src = Path(local)
        suffix = src.suffix if src.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"} else ".png"
        asset_root.mkdir(parents=True, exist_ok=True)
        dst = asset_root / f"{asset_id}{suffix}"
        shutil.copy2(src, dst)
        event.track_temporary_local_file(str(dst))
        record["path"] = str(dst)
    elif source_url.startswith(("http://", "https://")):
        record["url"] = source_url
    else:
        # Covers base64/file URI and unusual adapters. Resolve now, before the
        # originating handler gets a chance to delete its temporary output.
        resolved = Path(await comp.convert_to_file_path())
        suffix = resolved.suffix if resolved.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"} else ".png"
        asset_root.mkdir(parents=True, exist_ok=True)
        dst = asset_root / f"{asset_id}{suffix}"
        shutil.copy2(resolved, dst)
        event.track_temporary_local_file(str(dst))
        record["path"] = str(dst)
    assets[asset_id] = record
    return asset_id


async def _capture_file(event, comp: File, asset_root: Path, assets: dict) -> str:
    asset_id = "file-" + uuid.uuid4().hex[:10]
    source = await comp.get_file()
    if not source:
        raise ValueError(f"文件产物 {getattr(comp, 'name', '') or asset_id} 无法读取")
    src = Path(source)
    suffix = src.suffix or Path(str(getattr(comp, "name", "") or "")).suffix
    asset_root.mkdir(parents=True, exist_ok=True)
    dst = asset_root / f"{asset_id}{suffix}"
    shutil.copy2(src, dst)
    event.track_temporary_local_file(str(dst))
    assets[asset_id] = {
        "kind": "file",
        "path": str(dst),
        "name": str(getattr(comp, "name", "") or src.name or dst.name),
    }
    return asset_id


async def _capture_chain(event, chain, asset_root: Path, assets: dict, texts: list[str], media: list[dict], content: list[dict] | None = None, direct_rich: list | None = None) -> None:
    if chain is None:
        return
    components = getattr(chain, "chain", chain)
    if components is None:
        return
    for comp in components:
        if isinstance(comp, Plain):
            if comp.text:
                value = str(comp.text)
                texts.append(value)
                if content is not None:
                    content.append({"type": "text", "text": value})
        elif isinstance(comp, Image):
            aid = await _capture_image(event, comp, asset_root, assets)
            item = {"id": aid, "type": "image"}
            media.append(item)
            if content is not None:
                content.append(dict(item))
        elif isinstance(comp, File):
            aid = await _capture_file(event, comp, asset_root, assets)
            item = {"id": aid, "type": "file", "name": assets[aid].get("name", "")}
            media.append(item)
            if content is not None:
                content.append(dict(item))
        elif isinstance(comp, Music):
            # Music cards are ephemeral transport actions, not assets the model
            # should re-present later. Preserve the exact component and deliver
            # it through the original event.send after the formal handler ends.
            item = {"type": "music", "delivery": "direct"}
            media.append(item)
            if content is not None:
                content.append(dict(item))
            if direct_rich is not None:
                direct_rich.append(comp)
        else:
            item = {"type": comp.__class__.__name__.lower(), "note": "Use the direct command for this rich output."}
            media.append(item)
            if content is not None:
                content.append(dict(item))


async def _find_handler(event, plugin_context, body: str, target_capability: str):
    cfg = plugin_context.get_config(umo=event.unified_msg_origin)
    denied = False
    for md in star_handlers_registry.get_handlers_by_event_type(EventType.AdapterMessageEvent):
        star = star_map.get(md.handler_module_path)
        plugin_name = str(getattr(star, "name", "") or "") if star else ""
        if plugin_name == "doge_legacy":
            continue
        if plugin_name.startswith("doge_") and not await is_plugin_enabled(event.unified_msg_origin, plugin_name):
            continue
        # Generic bridge should invoke real command handlers, not arbitrary
        # passive message listeners or top-level command-group placeholders.
        if not any(isinstance(f, CommandFilter) for f in md.event_filters):
            continue

        event._extras.pop("parsed_params", None)
        passed = True
        try:
            for filt in md.event_filters:
                if not filt.filter(event, cfg):
                    passed = False
                    break
        except ValueError:
            passed = False
        if not passed:
            continue

        # A handler can match an alias that maps elsewhere. Require that the
        # formal registry recognizes the exact message as the requested leaf.
        inv = match_invocation("/" + body)
        if inv and inv.capability_id == target_capability:
            return md, dict(event.get_extra("parsed_params", {}) or {})
    if denied:
        raise PermissionError("当前用户没有这个功能的权限")
    return None, {}


async def execute_formal_command(run_context: ContextWrapper[AstrAgentContext], command: str) -> str:
    command = _normalize_command(command)
    inv = match_invocation(command)
    if inv is None:
        raise ValueError(f"不是可执行的正式 Doge 指令，或缺少必要参数。请先查看 {_likely_help(command)}")
    op = operation_by_id(inv.capability_id) or {}
    event = run_context.context.event
    plugin_context = run_context.context.context
    body = command[1:].strip()

    old_message = event.message_str
    old_wake = getattr(event, "is_wake", False)
    old_at = getattr(event, "is_at_or_wake_command", False)
    old_result = event.get_result()
    old_force = getattr(event, "_force_stopped", False)
    old_parsed_exists = "parsed_params" in event.get_extra(default={})
    old_parsed = event.get_extra("parsed_params")
    old_send = event.send

    texts: list[str] = []
    media: list[dict] = []
    content: list[dict] = []
    direct_rich: list = []
    assets = event.get_extra(_ASSET_KEY)
    if not isinstance(assets, dict):
        assets = {}
        event.set_extra(_ASSET_KEY, assets)
    asset_root = Path(plugin_context.get_config().get("data_dir", "") or "/tmp")
    # Use AstrBot's tracked runtime temp area only through event lifetime.
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
        asset_root = Path(get_astrbot_temp_path()) / "doge-agent-assets"
    except Exception:
        asset_root = Path("/tmp/doge-agent-assets")

    async def capture_send(message) -> None:
        await _capture_chain(event, message, asset_root, assets, texts, media, content, direct_rich)

    try:
        event.message_str = body
        event.is_wake = True
        event.is_at_or_wake_command = True
        event.clear_result()
        event._force_stopped = False
        # Suppress direct platform sends while the Agent is collecting evidence.
        # The model can later call doge_present for selected media.
        event.send = capture_send

        md, params = await _find_handler(event, plugin_context, body, inv.capability_id)
        if md is None:
            raise RuntimeError(f"正式能力 {inv.capability_id} 当前没有可调用的活动 handler；可能已被本群关闭")

        ready = md.handler(event, **params)
        if inspect.isasyncgen(ready):
            async for ret in ready:
                if isinstance(ret, MessageEventResult):
                    await _capture_chain(event, ret, asset_root, assets, texts, media, content, direct_rich)
                elif isinstance(ret, str):
                    texts.append(ret)
        elif inspect.isawaitable(ready):
            ret = await ready
            if isinstance(ret, MessageEventResult):
                await _capture_chain(event, ret, asset_root, assets, texts, media, content, direct_rich)
            elif isinstance(ret, str):
                texts.append(ret)
        elif ready is not None:
            texts.append(str(ready))

        # Some wrappers communicate only through event.set_result().
        residual = event.get_result()
        if residual is not None and residual is not old_result:
            await _capture_chain(event, residual, asset_root, assets, texts, media, content, direct_rich)
    finally:
        event.send = old_send
        event.message_str = old_message
        event.is_wake = old_wake
        event.is_at_or_wake_command = old_at
        event._force_stopped = old_force
        if old_result is None:
            event.clear_result()
        else:
            event.set_result(old_result)
        if old_parsed_exists:
            event.set_extra("parsed_params", old_parsed)
        else:
            event._extras.pop("parsed_params", None)

    # File-producing capabilities are explicit user requests for an artifact.
    # Send captured files immediately instead of asking the user to repeat the
    # raw command. Images remain selectable through doge_present.
    sent_files: list[str] = []
    for item in media:
        if item.get("type") != "file" or not item.get("id"):
            continue
        asset = assets.get(str(item["id"])) if isinstance(assets, dict) else None
        if not asset or asset.get("kind") != "file":
            continue
        path = Path(str(asset.get("path") or ""))
        if not path.exists():
            continue
        name = str(asset.get("name") or path.name)
        await old_send(MessageChain([File(name=name, file=str(path))]))
        sent_files.append(str(item["id"]))

    # Immediate rich transport outputs (currently native Music cards) are
    # delivered exactly once. Generator yield + residual event result can expose
    # the same component twice, so de-duplicate by its OneBot payload.
    rich_sent: list[dict] = []
    rich_seen: set[str] = set()
    for comp in direct_rich:
        try:
            payload = comp.toDict()
            fingerprint = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        except Exception:
            payload = {"type": comp.__class__.__name__.lower()}
            fingerprint = repr(payload)
        if fingerprint in rich_seen:
            continue
        rich_seen.add(fingerprint)
        await old_send(MessageChain([comp]))
        rich_sent.append(payload)

    # De-duplicate text because generator yield + residual event result can point
    # to the same MessageEventResult in wrapper-heavy plugins.
    deduped: list[str] = []
    seen: set[str] = set()
    for text in texts:
        value = str(text).strip()
        if value and value not in seen:
            seen.add(value)
            deduped.append(value)
    joined = "\n\n".join(deduped)
    if len(joined) > _MAX_TOOL_TEXT:
        joined = joined[:_MAX_TOOL_TEXT] + "\n…[truncated for Agent synthesis]"

    payload = {
        "capability_id": inv.capability_id,
        "summary": op.get("summary", ""),
        "text": joined,
        "media": media,
        "content": content,
        "files_sent": sent_files,
        "rich_sent": rich_sent,
        "direct_command": command,
        "guidance": (
            "Synthesize the useful parts instead of dumping this object. "
            "File outputs listed in files_sent and rich outputs listed in rich_sent have already been delivered to the user; do not ask them to repeat the command. "
            "The content field preserves the original text/media order. "
            "For explanations with multiple rendered images, use doge_present.blocks to send a true text-image-text sequence instead of batching all images at the end. "
            "Only present image media that materially improves the answer. Mention direct_command only when an explicit raw command would genuinely help the user."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


@dataclass
class DogeMessageHistoryTool(FunctionTool[AstrAgentContext]):
    name: str = "search_message_history"
    description: str = (
        "检索较早的聊天记录，用于回忆此前讨论、核对原话、确认谁说过什么以及消息发生时间。"
        "不要在普通聊天中例行调用；只有当前上下文不足以可靠回答历史问题时使用。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "要检索的原话、人物、话题或关键词"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 30, "description": "最多返回多少条命中，默认 12"},
        },
        "required": ["query"],
    })

    @staticmethod
    def _content_text(content) -> tuple[str, str]:
        if isinstance(content, str):
            try:
                content = json.loads(content)
            except Exception:
                return "", content.strip()
        if not isinstance(content, dict):
            return "", str(content or "").strip()
        role = str(content.get("type") or "")
        parts: list[str] = []
        for item in content.get("message") or []:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("type") or "")
            if kind == "plain":
                text = str(item.get("text") or "").strip()
                if text:
                    parts.append(text)
            elif kind == "at":
                label = str(item.get("name") or item.get("user_id") or "").strip()
                if label:
                    parts.append("@" + label)
            elif kind == "reply":
                quoted = str(item.get("text") or "").strip()
                if quoted:
                    parts.append("[引用] " + quoted)
        return role, " ".join(parts).strip()

    @staticmethod
    def _local_time(value) -> str:
        if not isinstance(value, datetime):
            return ""
        # AstrBot persists SQLite timestamps as UTC-naive datetimes.
        dt = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
        return dt.astimezone(ZoneInfo("Asia/Shanghai")).isoformat(sep=" ", timespec="seconds")

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs):
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "query 不能为空"}, ensure_ascii=False)
        event = context.context.event
        if not event.get_group_id():
            return json.dumps({"query": query, "results": []}, ensure_ascii=False)

        # Security boundary: select the ledger by the event's own UMO first.
        # The model never supplies or controls a group/session identifier.
        platform_id = str(event.get_platform_id() or "")
        ledger_id = str(event.unified_msg_origin)
        manager = context.context.context.message_history_manager
        limit = max(1, min(int(kwargs.get("limit") or 12), 30))
        needle = query.casefold()
        terms = [x for x in re.split(r"\s+", needle) if x]
        matches: list[dict] = []
        max_pages, page_size = 50, 200
        for page in range(1, max_pages + 1):
            rows = await manager.get(platform_id=platform_id, user_id=ledger_id, page=page, page_size=page_size)
            if not rows:
                break
            for item in reversed(rows):  # newest first inside each page
                role, text = self._content_text(getattr(item, "content", None))
                if not text:
                    continue
                folded = text.casefold()
                if needle not in folded and not (terms and all(t in folded for t in terms)):
                    continue
                matches.append({
                    "time": self._local_time(getattr(item, "created_at", None)),
                    "sender": str(getattr(item, "sender_name", "") or ""),
                    "sender_id": str(getattr(item, "sender_id", "") or ""),
                    "role": role,
                    "text": text[:2400],
                })
                if len(matches) >= limit:
                    break
            if len(matches) >= limit or len(rows) < page_size:
                break
        return json.dumps({"query": query, "results": matches}, ensure_ascii=False)


@dataclass
class DogeCapabilitySearchTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_capability_search"
    description: str = (
        "按自然语言检索 Doge 正式能力 registry，返回最相关的精确指令语法、参数、附件要求和示例。"
        "询问 Doge 当前是否支持某功能、功能是否已完善/升级、当前参数或限制时，registry 是当前真值并覆盖旧会话中的历史说法；不要凭记忆回答旧版本能力。"
        "当你知道用户想做什么但不确定 Doge 的具体命令时先调用它；先用用户原语言搜索一次，只有候选不明确时才换词再次搜索，不要中英文重复搜同一件事。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "能力需求或关键词，例如 西夏文翻译、RRPL语法、符号积分、生命游戏GIF、CIF晶体、Lean形式化",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 12,
                "description": "返回候选数，默认 6",
            },
        },
        "required": ["query"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs):
        query = str(kwargs.get("query") or "").strip()
        if not query:
            return json.dumps({"error": "query 不能为空"}, ensure_ascii=False)
        limit = int(kwargs.get("limit") or 6)
        results = search_capabilities(query, limit=limit)
        return json.dumps(
            {
                "query": query,
                "results": results,
                "guidance": (
                    "Choose the capability that actually matches the user's intent, fill all required parameters/inputs, "
                    "then call doge_capability with the documented command. Search again if these candidates are ambiguous."
                ),
            },
            ensure_ascii=False,
        )


@dataclass
class DogeCapabilityTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_capability"
    description: str = (
        "调用任意已安装且非 Legacy 的 Doge 正式指令。文本/图片返回给上层 Agent；文件产物会自动发送给用户并在结果中标记 files_sent。"
        "command 必须是 capability inventory 中的完整可执行指令并包含必要参数。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "完整 Doge 指令，例如 /math oeis 1,1,2,3,5,8 或 /lab ising 2.269",
            },
        },
        "required": ["command"],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs):
        return await execute_formal_command(context, str(kwargs.get("command") or ""))


@dataclass
class DogePresentTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_present"
    description: str = (
        "展示 doge_capability 捕获的精选图片，并支持 blocks 按顺序组织文字→图片→文字。"
        "多公式解释优先用 blocks 保留交替结构；不要把所有图片无脑堆到答案末尾。"
    )
    parameters: dict = Field(default_factory=lambda: {
        "type": "object",
        "properties": {
            "asset_ids": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 6,
                "description": "兼容模式：按给定顺序展示 image asset id",
            },
            "blocks": {
                "type": "array",
                "minItems": 1,
                "maxItems": 16,
                "items": {
                    "type": "object",
                    "properties": {
                        "type": {"type": "string", "enum": ["text", "image"]},
                        "text": {"type": "string"},
                        "asset_id": {"type": "string"},
                    },
                    "required": ["type"],
                },
                "description": "有序混合块；text 用 text 字段，image 用 asset_id。适合文字/公式图交替。",
            },
            "caption": {"type": "string", "description": "可选的最后一行简短说明"},
        },
        "required": [],
    })

    async def call(self, context: ContextWrapper[AstrAgentContext], **kwargs):
        event = context.context.event
        assets = event.get_extra(_ASSET_KEY, {})
        ids = [str(x) for x in (kwargs.get("asset_ids") or [])][:6]
        blocks = list(kwargs.get("blocks") or [])[:16]
        chain = []
        missing = []

        def append_image(aid: str) -> None:
            item = assets.get(aid) if isinstance(assets, dict) else None
            if not item or item.get("kind") != "image":
                missing.append(aid)
                return
            if item.get("path") and Path(item["path"]).exists():
                chain.append(Image.fromFileSystem(item["path"]))
            elif item.get("url"):
                chain.append(Image.fromURL(item["url"]))
            else:
                missing.append(aid)

        if blocks:
            for block in blocks:
                if not isinstance(block, dict):
                    continue
                kind = str(block.get("type") or "").lower()
                if kind == "text":
                    text = str(block.get("text") or "").strip()
                    if text:
                        chain.append(Plain(text))
                elif kind == "image":
                    aid = str(block.get("asset_id") or "")
                    if aid:
                        append_image(aid)
        else:
            for aid in ids:
                append_image(aid)
        caption = str(kwargs.get("caption") or "").strip()
        if caption:
            chain.append(Plain(caption))
        if not chain:
            return "No selected presentation content is available: " + ", ".join(missing or ids)
        return await _send_presentation_bounded(event, chain)
