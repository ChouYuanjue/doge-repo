from __future__ import annotations

import inspect
import json
import shutil
import uuid
from pathlib import Path

from pydantic import Field
from pydantic.dataclasses import dataclass

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.message.components import File, Image, Plain
from astrbot.core.message.message_event_result import MessageChain, MessageEventResult
from astrbot.core.star.filter.command import CommandFilter
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import EventType, star_handlers_registry

from .capabilities import match_invocation, operation_by_id, operations_for_prefix, search_capabilities
from .module_control import is_plugin_enabled

_ASSET_KEY = "_doge_agent_assets"
_MAX_TOOL_TEXT = 18000


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


async def _capture_chain(event, chain, asset_root: Path, assets: dict, texts: list[str], media: list[dict], content: list[dict] | None = None) -> None:
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
        await _capture_chain(event, message, asset_root, assets, texts, media, content)

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
                    await _capture_chain(event, ret, asset_root, assets, texts, media, content)
                elif isinstance(ret, str):
                    texts.append(ret)
        elif inspect.isawaitable(ready):
            ret = await ready
            if isinstance(ret, MessageEventResult):
                await _capture_chain(event, ret, asset_root, assets, texts, media, content)
            elif isinstance(ret, str):
                texts.append(ret)
        elif ready is not None:
            texts.append(str(ready))

        # Some wrappers communicate only through event.set_result().
        residual = event.get_result()
        if residual is not None and residual is not old_result:
            await _capture_chain(event, residual, asset_root, assets, texts, media, content)
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
        "direct_command": command,
        "guidance": (
            "Synthesize the useful parts instead of dumping this object. "
            "File outputs listed in files_sent have already been delivered to the user; do not ask them to repeat the command. "
            "The content field preserves the original text/media order. "
            "For explanations with multiple rendered images, use doge_present.blocks to send a true text-image-text sequence instead of batching all images at the end. "
            "Only present image media that materially improves the answer. Mention direct_command only when an explicit raw command would genuinely help the user."
        ),
    }
    return json.dumps(payload, ensure_ascii=False)


@dataclass
class DogeCapabilitySearchTool(FunctionTool[AstrAgentContext]):
    name: str = "doge_capability_search"
    description: str = (
        "按自然语言检索 Doge 正式能力 registry，返回最相关的精确指令语法、参数、附件要求和示例。"
        "当你知道用户想做什么但不确定 Doge 的具体命令时先调用它；不要凭记忆编造命令。先用用户原语言搜索一次，只有候选不明确时才换词再次搜索，不要中英文重复搜同一件事。"
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
        result = MessageEventResult(chain=chain)
        result.use_markdown(False)
        return result
