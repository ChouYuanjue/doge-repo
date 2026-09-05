from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from types import SimpleNamespace

from astrbot.api import logger
from astrbot.core.utils.active_event_registry import active_event_registry


class _ParallelExecutionLockManager:
    """Compatibility object for AstrBot's coarse per-session agent lock.

    AstrBot 4.27 acquires this lock across the whole provider + tool loop. Doge
    deliberately lets independent message events run concurrently and restores
    consistency only while committing history.
    """

    @asynccontextmanager
    async def acquire_lock(self, _session_id: str):
        yield


class _CaptureConversationManager:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    async def update_conversation(self, *args, **kwargs):
        self.calls.append((args, dict(kwargs)))


def _common_prefix_len(a: list, b: list) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def merge_parallel_history(base: list, current: list, proposed: list) -> tuple[list, str]:
    """Merge one completed run into the latest persisted conversation.

    `base` is the history snapshot visible when the run started, `proposed` is
    what AstrBot's original saver wanted to write, and `current` is the newest
    DB history at commit time.
    """
    base = list(base or [])
    current = list(current or [])
    proposed = list(proposed or [])

    # Normal path: the original saver preserved the run's starting snapshot.
    if len(proposed) >= len(base) and proposed[: len(base)] == base:
        tail = proposed[len(base) :]
        if not tail:
            return current, "no-tail"
        # Idempotence: do not append the exact same run twice.
        if len(current) >= len(tail) and current[-len(tail) :] == tail:
            return current, "already-present"
        return current + tail, "append-tail"

    # Context compaction/checkpoint rewriting may make proposed not start with
    # the original serialized base. If no concurrent writer changed the DB,
    # retain AstrBot's exact overwrite semantics.
    if current == base:
        return proposed, "original-overwrite"

    # Concurrent writer + rewritten history: preserve both sides rather than
    # dropping the completed turn. Append only the portion that diverges from
    # the latest current prefix. This is deliberately conservative and logged.
    lcp = _common_prefix_len(current, proposed)
    tail = proposed[lcp:]
    if not tail:
        return current, "rewritten-already-present"
    if len(current) >= len(tail) and current[-len(tail) :] == tail:
        return current, "rewritten-duplicate"
    return current + tail, "rewritten-merge"


_commit_locks: dict[str, asyncio.Lock] = {}
_install_lock = asyncio.Lock()
_installed = False
_original_save = None


def _commit_lock(cid: str) -> asyncio.Lock:
    lock = _commit_locks.get(cid)
    if lock is None:
        lock = asyncio.Lock()
        _commit_locks[cid] = lock
    return lock


async def _parallel_save_to_history(self, event, req, llm_response, all_messages, runner_stats, user_aborted=False):
    global _original_save
    original = _original_save
    if original is None:
        raise RuntimeError("parallel agent patch not initialized")

    # Reuse AstrBot's own saver unchanged, but redirect its update to a capture
    # object. This preserves checkpoint/tool/abort semantics across AstrBot minor
    # releases without duplicating that logic in Doge.
    capture = _CaptureConversationManager()
    proxy = SimpleNamespace(conv_manager=capture)
    await original(proxy, event, req, llm_response, all_messages, runner_stats, user_aborted)
    if not capture.calls:
        return

    for args, kwargs in capture.calls:
        history = kwargs.get("history")
        conversation_id = kwargs.get("conversation_id")
        unified_msg_origin = kwargs.get("unified_msg_origin")
        if conversation_id is None and len(args) >= 2:
            conversation_id = args[1]
        if unified_msg_origin is None and args:
            unified_msg_origin = args[0]
        if not conversation_id:
            conversation_id = getattr(getattr(req, "conversation", None), "cid", None)
        if not unified_msg_origin:
            unified_msg_origin = event.unified_msg_origin

        # If the original saver ever emits a metadata-only update, pass it
        # through under the same short commit lock.
        if history is None or not conversation_id:
            async with _commit_lock(str(conversation_id or unified_msg_origin)):
                await self.conv_manager.update_conversation(*args, **kwargs)
            continue

        try:
            base = json.loads(getattr(req.conversation, "history", "") or "[]")
            if not isinstance(base, list):
                base = []
        except Exception:
            base = []

        cid = str(conversation_id)
        async with _commit_lock(cid):
            conv = await self.conv_manager.db.get_conversation_by_id(cid=cid)
            current = list(getattr(conv, "content", None) or []) if conv else []
            merged, mode = merge_parallel_history(base, current, list(history))
            if mode.startswith("rewritten"):
                logger.warning(
                    "Doge parallel history used conservative merge cid=%s mode=%s base=%d current=%d proposed=%d",
                    cid,
                    mode,
                    len(base),
                    len(current),
                    len(history),
                )
            await self.conv_manager.update_conversation(
                str(unified_msg_origin),
                cid,
                history=merged,
                token_usage=kwargs.get("token_usage"),
            )


def _runner_event(runner):
    return getattr(getattr(getattr(runner, "run_context", None), "context", None), "event", None)


def _parallel_register_active_runner(_umo: str, runner) -> None:
    """Register each concurrent Agent by its owning event, never in a UMO single slot."""
    event = _runner_event(runner)
    if event is not None:
        active_event_registry.register_agent_stop_callback(event, runner.request_stop)


def _parallel_unregister_active_runner(_umo: str, runner) -> None:
    """Unregister exactly this runner even when sibling Agents share the same UMO."""
    event = _runner_event(runner)
    if event is not None:
        active_event_registry.unregister_agent_stop_callback(event)


async def install_parallel_agent_patch() -> None:
    """Install Doge's AstrBot-4.27 parallel-session compatibility patch once."""
    global _installed, _original_save
    if _installed:
        return
    async with _install_lock:
        if _installed:
            return
        from astrbot.core.pipeline.process_stage.method.agent_sub_stages import internal

        if getattr(internal, "_doge_parallel_agent_patch", False):
            _installed = True
            return

        _original_save = internal.InternalAgentSubStage._save_to_history
        internal.InternalAgentSubStage._save_to_history = _parallel_save_to_history
        internal.session_lock_manager = _ParallelExecutionLockManager()

        # AstrBot's follow-up helper stores only one active runner per UMO. That
        # model is incompatible with Doge's independent concurrent requests.
        # The framework's active_event_registry is already multi-event, so bind
        # stop callbacks there directly and unregister each runner independently.
        internal.register_active_runner = _parallel_register_active_runner
        internal.unregister_active_runner = _parallel_unregister_active_runner

        # Same-sender follow-up capture would fold a later message into the older
        # runner. Doge intentionally starts a fresh Agent for every woken message.
        internal.try_capture_follow_up = lambda _event: None
        try:
            from astrbot.core.pipeline.process_stage import follow_up
            follow_up._ACTIVE_AGENT_RUNNERS.clear()
        except Exception:
            pass
        internal._doge_parallel_agent_patch = True
        _installed = True
        logger.info(
            "Doge parallel agent patch active: independent message runners + merge-only history commit"
        )
