from __future__ import annotations

import hashlib
import shutil
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from astrbot.core.message.components import File, Image, Reply
from astrbot.core.utils.session_waiter import SessionController, session_waiter


@dataclass(frozen=True, slots=True)
class ResolvedMaterial:
    kind: str
    path: str
    source: str  # current / reply / recent / followup
    message_id: str = ""
    sender_id: str = ""


@dataclass(slots=True)
class _CachedMaterial:
    kind: str
    path: str
    created_at: float
    message_id: str
    sender_id: str


class MaterialCache:
    """Short-lived, relationship-local material memory.

    Only media bytes and minimal routing metadata are cached. Message text is
    never stored here. Current/reply media always wins; recent media is only a
    fallback for the same sender in the same AstrBot session.
    """

    def __init__(self, root: Path | None = None, *, ttl_s: float = 300.0, max_per_key: int = 6):
        self.root = Path(root or "/tmp/doge-material-cache")
        self.ttl_s = float(ttl_s)
        self.max_per_key = int(max_per_key)
        self._recent: dict[tuple[str, str, str], deque[_CachedMaterial]] = defaultdict(deque)

    def configure(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _sender(event) -> str:
        try:
            return str(event.get_sender_id() or "")
        except Exception:
            return ""

    @staticmethod
    def _message_id(event) -> str:
        return str(getattr(getattr(event, "message_obj", None), "message_id", "") or "")

    @staticmethod
    async def _path(component, kind: str) -> str | None:
        try:
            if kind == "image" and isinstance(component, Image):
                path = await component.convert_to_file_path()
            elif kind == "file" and isinstance(component, File):
                path = await component.get_file()
            else:
                return None
        except Exception:
            return None
        if not path:
            return None
        p = Path(str(path))
        return str(p) if p.exists() and p.is_file() else None

    @staticmethod
    def _components(event, kind: str) -> tuple[list, list]:
        cls = Image if kind == "image" else File
        current: list = []
        quoted: list = []
        for component in event.get_messages():
            if isinstance(component, cls):
                current.append(component)
            elif isinstance(component, Reply) and component.chain:
                quoted.extend(x for x in component.chain if isinstance(x, cls))
        return current, quoted

    def _prune(self) -> None:
        now = time.time()
        empty = []
        for key, items in self._recent.items():
            while items and (now - items[0].created_at > self.ttl_s or not Path(items[0].path).exists()):
                old = items.popleft()
                Path(old.path).unlink(missing_ok=True)
            while len(items) > self.max_per_key:
                old = items.popleft()
                Path(old.path).unlink(missing_ok=True)
            if not items:
                empty.append(key)
        for key in empty:
            self._recent.pop(key, None)

    async def remember_event(self, event) -> None:
        """Persist top-level inbound media long enough for a following command.

        Reply-chain media is deliberately not cached as a user's own recent
        material; explicit replies remain available directly through Reply.chain.
        """
        self._prune()
        sender = self._sender(event)
        if not sender:
            return
        umo = str(event.unified_msg_origin or "")
        message_id = self._message_id(event)
        for kind, cls in (("image", Image), ("file", File)):
            for component in event.get_messages():
                if not isinstance(component, cls):
                    continue
                src = await self._path(component, kind)
                if not src:
                    continue
                source = Path(src)
                try:
                    size = source.stat().st_size
                except OSError:
                    continue
                # Avoid turning the short material cache into a generic file store.
                if size > 32 * 1024 * 1024:
                    continue
                suffix = source.suffix[:12] if source.suffix else (".jpg" if kind == "image" else ".bin")
                digest = hashlib.sha256(f"{umo}\0{sender}\0{message_id}\0{src}".encode()).hexdigest()[:20]
                folder = self.root / hashlib.sha256(f"{umo}\0{sender}".encode()).hexdigest()[:16]
                folder.mkdir(parents=True, exist_ok=True)
                dst = folder / f"{digest}{suffix}"
                try:
                    if source.resolve() != dst.resolve():
                        shutil.copy2(source, dst)
                except OSError:
                    continue
                key = (umo, sender, kind)
                items = self._recent[key]
                if not any(x.message_id == message_id and x.path == str(dst) for x in items):
                    items.append(_CachedMaterial(kind, str(dst), time.time(), message_id, sender))
        self._prune()

    async def resolve(self, event, kind: str, *, needed: int = 1, include_recent: bool = True) -> list[ResolvedMaterial]:
        if kind not in {"image", "file"}:
            raise ValueError(f"unsupported material kind: {kind}")
        self._prune()
        needed = max(1, int(needed))
        current, quoted = self._components(event, kind)
        sender = self._sender(event)
        message_id = self._message_id(event)
        umo = str(event.unified_msg_origin or "")
        out: list[ResolvedMaterial] = []
        seen: set[str] = set()

        async def add_components(components: list, source: str) -> None:
            for component in components:
                path = await self._path(component, kind)
                if not path:
                    continue
                real = str(Path(path).resolve())
                if real in seen:
                    continue
                seen.add(real)
                out.append(ResolvedMaterial(kind, path, source, message_id, sender))
                if len(out) >= needed:
                    return

        # An attachment on the command itself is most explicit. A reply is the
        # next strongest signal, then same-sender recent material.
        await add_components(current, "current")
        if len(out) < needed:
            await add_components(quoted, "reply")

        if include_recent and len(out) < needed and sender:
            for item in reversed(self._recent.get((umo, sender, kind), ())):
                if item.message_id and item.message_id == message_id:
                    continue
                if not Path(item.path).exists():
                    continue
                real = str(Path(item.path).resolve())
                if real in seen:
                    continue
                seen.add(real)
                out.append(ResolvedMaterial(kind, item.path, "recent", item.message_id, item.sender_id))
                if len(out) >= needed:
                    break
        return out[:needed]

    def context_summary(self, event) -> str:
        """Small non-path material cue for the Agent system prompt."""
        self._prune()
        current_images, reply_images = self._components(event, "image")
        current_files, reply_files = self._components(event, "file")
        sender = self._sender(event)
        umo = str(event.unified_msg_origin or "")
        message_id = self._message_id(event)

        def recent_count(kind: str) -> int:
            if not sender:
                return 0
            return sum(
                1 for x in self._recent.get((umo, sender, kind), ())
                if x.message_id != message_id and Path(x.path).exists()
            )

        bits = []
        if current_images: bits.append(f"current images={len(current_images)}")
        if reply_images: bits.append(f"quoted images={len(reply_images)}")
        if recent_count("image"): bits.append(f"recent same-sender images={recent_count('image')}")
        if current_files: bits.append(f"current files={len(current_files)}")
        if reply_files: bits.append(f"quoted files={len(reply_files)}")
        if recent_count("file"): bits.append(f"recent same-sender files={recent_count('file')}")
        if not bits:
            return ""
        return (
            "# Available material context\n"
            + "; ".join(bits)
            + ". Doge tools can access the original pixels/files through the material resolver; vision captions are not the only access path. "
              "For tools requiring media, use the user's explicit current attachment first, then an explicit quoted attachment, then recent same-sender material. "
              "If none exists, the direct capability may wait briefly for the user's next attachment. Do not claim pixel/file access is unavailable when one of these sources exists."
        )


MATERIALS = MaterialCache()


async def wait_for_materials(event, kind: str, needed: int, initial: list[ResolvedMaterial] | None = None, *, timeout: int = 60) -> list[ResolvedMaterial]:
    collected = list(initial or [])
    if len(collected) >= needed:
        return collected[:needed]
    label = "图片" if kind == "image" else "文件"
    await event.send(event.plain_result(f"还需要 {needed-len(collected)} 个{label}；{timeout} 秒内继续发送，输入 cancel 取消。"))
    original_sender = MATERIALS._sender(event)

    @session_waiter(timeout=timeout, record_history_chains=False)
    async def waiter(controller: SessionController, incoming):
        incoming_sender = MATERIALS._sender(incoming)
        if original_sender and incoming_sender and incoming_sender != original_sender:
            controller.keep(timeout=timeout, reset_timeout=False)
            return
        if (incoming.message_str or "").strip().lower() in {"cancel", "取消"}:
            controller.stop()
            return
        fresh = await MATERIALS.resolve(incoming, kind, needed=needed-len(collected), include_recent=False)
        for item in fresh:
            collected.append(ResolvedMaterial(item.kind, item.path, "followup", item.message_id, item.sender_id))
        await MATERIALS.remember_event(incoming)
        if len(collected) >= needed:
            controller.stop()
        else:
            await incoming.send(incoming.plain_result(f"已收到 {len(collected)}/{needed} 个{label}。"))
            controller.keep(timeout=timeout, reset_timeout=True)

    try:
        await waiter(event)
    except TimeoutError as exc:
        raise ValueError(f"等待{label}超时") from exc
    if len(collected) < needed:
        raise ValueError(f"没有收到足够的{label}")
    return collected[:needed]
